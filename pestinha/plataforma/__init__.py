"""
PLATAFORMA - a única parte do código que conhece o sistema operacional.

Cada sistema tem um módulo com as mesmas funções (windows.py, macos.py, linux.py, hyprland.py).
Este arquivo escolhe o certo na importação. Os retângulos são em pixels físicos (o app divide pelo dpr).

    ocioso_segundos()            segundos desde o último teclado ou mouse
    processo_ativo()             nome (minúsculo) do programa em primeiro plano
    retangulo_ativo(escala)      retângulo da janela em primeiro plano, ou None
    tela_cheia()                 a janela em primeiro plano cobre o monitor inteiro
    janelas_visiveis(excluir, escala)   [(id, (l, t, r, b), maximizada)] de cima para baixo
    sem_foco_nativo(janela_id)   a janela do pet não rouba o foco (quando o sistema permite)
    iniciar_atalho(callback)     Ctrl+Alt+Shift+B; devolve True se registrou

Só no Windows, por enquanto (TEM_INICIO_AUTOMATICO diz se existe):
    inicia_com_sistema()         o programa está marcado para abrir ao entrar no sistema
    definir_inicio_com_sistema(ligado)   liga ou desliga isso; devolve True se conseguiu
"""

import os
import sys


def _no_hyprland():
    """Verdadeiro se a sessão é do Hyprland (variável de instância ou socket IPC presente)."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return True
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    pasta = os.path.join(base, "hypr")
    return os.path.isdir(pasta) and any(os.path.exists(os.path.join(pasta, d, ".socket.sock"))
                                       for d in os.listdir(pasta))


if sys.platform == "win32":
    from . import windows as _backend
elif sys.platform == "darwin":
    from . import macos as _backend
elif _no_hyprland():
    from . import hyprland as _backend
else:
    from . import linux as _backend

NOME_DO_SISTEMA = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")

ocioso_segundos = _backend.ocioso_segundos
processo_ativo = _backend.processo_ativo
retangulo_ativo = _backend.retangulo_ativo
tela_cheia = _backend.tela_cheia
janelas_visiveis = _backend.janelas_visiveis
sem_foco_nativo = _backend.sem_foco_nativo
iniciar_atalho = _backend.iniciar_atalho

TEM_INICIO_AUTOMATICO = hasattr(_backend, "definir_inicio_com_sistema")
inicia_com_sistema = getattr(_backend, "inicia_com_sistema", lambda: False)
definir_inicio_com_sistema = getattr(_backend, "definir_inicio_com_sistema", lambda ligado: False)

# Só no Hyprland: mover as janelas do pet pelo compositor (o Qt não consegue sozinho).
mover_janela = getattr(_backend, "mover_janela", None)
configurar_janela = getattr(_backend, "configurar_janela", None)
