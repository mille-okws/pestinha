"""
Linux (Hyprland, Wayland): as leituras saem do `hyprctl` (JSON) e o pet se move
pelo `hl.dsp.window.move` do compositor, porque no Wayland o Qt não move a janela
sozinho (o `QWidget.move()` é ignorado pelo compositor).

O movimento vai direto pelo socket IPC do Hyprland (`$XDG_RUNTIME_DIR/hypr/$SIG/.socket.sock`),
não por um processo `hyprctl` a cada quadro: um fork processa ~7 ms, o socket ~0,1 ms.
Se o socket não existir, cai para o `hyprctl` (comando externo), mais lento mas funcional.

Limitações conhecidas no Hyprland:
- o tempo ocioso não é exposto pelo compositor: `ocioso_segundos()` devolve 0
  (o pet acha que você está sempre ativo, como no Linux/Wayland sem o xprintidle);
- o atalho global de pânico não pode ser registrado pelo app: precisa de um `bind`
  no `hyprland.conf` que mande o sinal (ver `iniciar_atalho`);
- os `excluir` de `janelas_visiveis` são ids do X11 e não existem aqui: as janelas
  do próprio processo já são excluídas pelo pid.
"""

import json
import os
import socket

import psutil

from ..log import log
from ._comum import rodar

LARGURA_MINIMA, ALTURA_MINIMA = 120, 60

# muda de quadro para quadro: cache do endereço da janela do pet no compositor
_enderecos = {}          # (pid, titulo, largura, altura) -> "0x..."
_ultimo_move = {}        # endereço -> (x, y) já pedido
_configuradas = set()    # endereços já deixados flutuantes/fixados


# ============================================================
# Leitura do compositor (subprocesso hyprctl, 2x por segundo no app)
# ============================================================

def _hyprctl_json(*args):
    """Saída JSON do `hyprctl`, ou None se ele não existe, falhou ou demorou demais."""
    texto = rodar(["hyprctl", "-j", *args], tempo=2.0)
    if texto is None:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


def _clientes():
    """Todos os clientes do compositor (`hyprctl -j clients`), ou []."""
    dados = _hyprctl_json("clients")
    return dados if isinstance(dados, list) else []


def _ativo():
    """Cliente em primeiro plano (`hyprctl -j activewindow`), ou None."""
    dados = _hyprctl_json("activewindow")
    return dados if isinstance(dados, dict) and dados.get("address") else None


# ============================================================
# Funções puras (testadas com saídas de exemplo, em qualquer sistema)
# ============================================================

def retangulo_de(cliente):
    """(l, t, r, b) a partir do `at`/`size` de um cliente, ou None se faltar algo."""
    try:
        x, y = cliente["at"]
        largura, altura = cliente["size"]
    except (KeyError, TypeError, ValueError):
        return None
    return (int(x), int(y), int(x) + int(largura), int(y) + int(altura))


def parse_clientes(clientes, meu_pid, escala=1.0):
    """[(id, (l, t, r, b), em_tela_cheia)] de cima para baixo (foco mais recente primeiro).

    Pula o próprio processo, clientes sem mapa e janelinhas menores que o mínimo
    (mesmo corte do backend X11). Nunca guarda título nem conteúdo: só geometria.
    """
    achadas = []
    for cliente in sorted(clientes, key=lambda c: c.get("focusHistoryID", 1 << 30)):
        if cliente.get("pid") == meu_pid or not cliente.get("mapped"):
            continue
        ret = retangulo_de(cliente)
        if ret is None:
            continue
        largura, altura = ret[2] - ret[0], ret[3] - ret[1]
        if largura < LARGURA_MINIMA or altura < ALTURA_MINIMA:
            continue
        try:
            janela_id = int(cliente["address"], 16)
        except (KeyError, TypeError, ValueError):
            continue
        achadas.append((janela_id, ret, bool(cliente.get("fullscreen"))))
    return achadas


def nome_do_processo(cliente):
    """Nome (minúsculo) do programa do cliente: processo via psutil, ou a classe."""
    try:
        return psutil.Process(int(cliente["pid"])).name().lower()
    except (KeyError, TypeError, ValueError, psutil.Error):
        pass
    classe = (cliente.get("class") or cliente.get("initialClass") or "").strip().lower()
    return classe or "unknown"


def cobre_monitor(retangulo, monitores):
    """Verdadeiro se o retângulo cobre algum monitor inteiro (tela cheia improvisada)."""
    if retangulo is None:
        return False
    for monitor in monitores or []:
        try:
            x, y, largura, altura = monitor["x"], monitor["y"], monitor["width"], monitor["height"]
        except (KeyError, TypeError):
            continue
        if (retangulo[0] <= x and retangulo[1] <= y
                and retangulo[2] >= x + largura and retangulo[3] >= y + altura):
            return True
    return False


# ============================================================
# Interface da plataforma (a mesma dos outros backends)
# ============================================================

def ocioso_segundos():
    """Tempo ocioso: o Hyprland não expõe isso por IPC. Devolve 0 (sempre ativo)."""
    return 0.0


def processo_ativo():
    """Nome do programa da janela ativa (`hyprctl -j activewindow` + psutil)."""
    cliente = _ativo()
    return nome_do_processo(cliente) if cliente else "unknown"


def retangulo_ativo(escala=1.0):
    """Retângulo da janela ativa, ou None se não houver janela ativa."""
    cliente = _ativo()
    return retangulo_de(cliente) if cliente else None


def tela_cheia():
    """Diz se a janela ativa está em tela cheia ou cobre o monitor inteiro."""
    cliente = _ativo()
    if cliente is None:
        return False
    if cliente.get("fullscreen"):
        return True
    monitores = _hyprctl_json("monitors")
    return cobre_monitor(retangulo_de(cliente), monitores if isinstance(monitores, list) else [])


def janelas_visiveis(excluir, escala=1.0):
    """Janelas visíveis de outros programas (as do próprio processo já saem pelo pid)."""
    return parse_clientes(_clientes(), os.getpid(), escala)


def sem_foco_nativo(janela_id):
    """O compositor já não dá foco a janela de ferramenta; nada a fazer aqui."""


def iniciar_atalho(callback):
    """
    O atalho global não pode ser registrado pelo app no Wayland. Para o pânico funcionar,
    ligue no `hyprland.conf`: `bind = CTRL ALT SHIFT, B, exec, pkill -SIGUSR1 -f pestinha`
    (o app escuta o SIGUSR1 como pânico quando neste backend). Devolve False.
    """
    log("[pânico] no Hyprland o atalho é um bind do compositor (ver plataforma/hyprland.py)")
    return False


# ============================================================
# Posicionamento das janelas do pet (só existe neste backend)
# ============================================================

def _socket_hyprland():
    """Caminho do socket IPC do Hyprland, ou None se não há instância ativa."""
    assinatura = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not assinatura:
        return None
    caminho = os.path.join(base, "hypr", assinatura, ".socket.sock")
    return caminho if os.path.exists(caminho) else None


def _pedir(texto):
    """Manda um pedido pelo socket IPC e devolve a resposta (texto), ou None."""
    caminho = _socket_hyprland()
    if caminho is None:
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(caminho)
            sock.sendall(texto.encode())
            resposta = b""
            while True:
                pedaco = sock.recv(65536)
                if not pedaco:
                    break
                resposta += pedaco
    except OSError:
        return None
    return resposta.decode(errors="replace")


def _endereco_da_janela(pid, titulo, largura, altura):
    """Endereço do cliente do compositor que é esta janela do pet (cacheado por pid)."""
    chave = (pid, titulo, largura, altura)
    if chave in _enderecos:
        return _enderecos[chave]
    # pid + título já identificam a janela (os títulos são únicos por janela do pet);
    # o tamanho pode não bater aqui porque a janela nova nasce tiled no Hyprland,
    # com o tamanho do workspace em vez do tamanho do widget.
    for cliente in _clientes():
        if cliente.get("pid") != pid:
            continue
        if titulo and cliente.get("title") == titulo:
            _enderecos[chave] = cliente["address"]
            return cliente["address"]
    for cliente in _clientes():
        if cliente.get("pid") != pid:
            continue
        if list(cliente.get("size") or []) != [largura, altura]:
            continue
        _enderecos[chave] = cliente["address"]
        return cliente["address"]
    return None


def _comando_move(endereco, x, y):
    """Lua do dispatcher de movimento (sintaxe nova do Hyprland, via `dispatch`)."""
    return f'hl.dsp.window.move({{x={int(x)}, y={int(y)}, relative=false, window="address:{endereco}"}})'


def mover_janela(pid, titulo, largura, altura, x, y):
    """
    Move a janela do pet para (x, y) pelo compositor. Verdadeiro se o pedido saiu.

    Vai pelo socket IPC (~0,1 ms, aguenta 60 quadros/s); sem socket, cai para o
    `hyprctl dispatch` (um processo por chamada, mais lento). Chamadas repetidas
    com a mesma coordenada não mandam nada de novo.
    """
    endereco = _endereco_da_janela(pid, titulo, largura, altura)
    if endereco is None:
        return False
    if endereco not in _configuradas:
        _configuradas.add(endereco)
        configurar_janela(pid, titulo, largura, altura)
    alvo = (int(x), int(y))
    if _ultimo_move.get(endereco) == alvo:
        return True
    _ultimo_move[endereco] = alvo
    comando = _comando_move(endereco, x, y)
    resposta = _pedir(f"dispatch {comando}")
    if resposta is not None:
        return "error" not in resposta
    return rodar(["hyprctl", "dispatch", comando], tempo=1.0) == "ok\n"


def configurar_janela(pid, titulo, largura, altura):
    """
    Deixa a janela flutuante, fixada (pin), por cima e sem decoração, uma vez só.
    Sem isso o compositor a trata como janela normal e o move não cola.
    """
    endereco = _endereco_da_janela(pid, titulo, largura, altura)
    if endereco is None:
        return False
    janela = f'address:{endereco}'
    for comando in (
        f'hl.dsp.window.float({{action="on", window="{janela}"}})',
        f'hl.dsp.window.resize({{x={int(largura)}, y={int(altura)}, relative=false, window="{janela}"}})',
        f'hl.dsp.window.pin({{action="on", window="{janela}"}})',
        f'hl.dsp.window.alter_zorder({{mode="top", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="decorate", value="0", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="border_size", value="0", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="rounding", value="0", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="no_blur", value="1", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="no_shadow", value="1", window="{janela}"}})',
        f'hl.dsp.window.set_prop({{prop="no_dim", value="1", window="{janela}"}})',
    ):
        _pedir(f"dispatch {comando}")
    return True
