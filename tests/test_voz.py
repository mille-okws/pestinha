"""
Voz: texto e emoção, cache, voz natural (motor e trabalhador do OmniVoice), instalação e a tela.

Nada aqui toca som nem carrega o modelo: a plataforma é falsa e o trabalhador é um script que fala
o mesmo protocolo. O teste com o modelo de verdade é o passo [4/4] do instalador.
"""
import json
import os
import sys
import textwrap
import time
import wave
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pestinha import config  # noqa: E402
from pestinha.mind import omnivoice_trabalhador as trab  # noqa: E402
from pestinha.mind import voz_instalacao as inst  # noqa: E402
from pestinha.mind.voz import ATRASO_MAXIMO_S, EMOCOES, Voz, com_emocao, para_fala  # noqa: E402
from pestinha.mind.voz_motor import MotorVoz, instalada, python_do_ambiente  # noqa: E402
from pestinha.paths import Paths  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


# ---------------- dublês ----------------

class ProcessoFalso:
    def __init__(self):
        self.parado = False

    def poll(self):
        return 0 if self.parado else None

    def terminate(self):
        self.parado = True


class SistemaFalso:
    """Faz o papel da plataforma: anota o que foi falado ou tocado, sem som."""
    TEM_VOZ = True

    def __init__(self):
        self.falas, self.toques, self.processos = [], [], []

    def falar(self, texto, voz=None):
        self.falas.append((texto, voz))
        return self._novo()

    def tocar_audio(self, caminho):
        self.toques.append(Path(caminho))
        return self._novo()

    def _novo(self):
        p = ProcessoFalso()
        self.processos.append(p)
        return p


class MotorFalso:
    """Faz o papel do MotorVoz: guarda os pedidos; `responder` simula o trabalhador terminando."""

    def __init__(self, instalado=True, rodando=True):
        self._instalado, self._rodando = instalado, rodando
        self.pedidos, self.ligou, self.desligou = [], 0, 0

    def instalado(self):
        return self._instalado

    def rodando(self):
        return self._rodando

    def ligar(self):
        self.ligou += 1

    def desligar(self):
        self.desligou += 1

    def pedir(self, pedido, ao_terminar):
        if not self._rodando:
            return False
        self.pedidos.append((pedido, ao_terminar))
        return True

    def responder(self, i=-1, ok=True):
        pedido, ao_terminar = self.pedidos[i]
        if ok:
            Path(pedido["saida"]).parent.mkdir(parents=True, exist_ok=True)
            Path(pedido["saida"]).write_bytes(b"RIFF....WAVE")
        ao_terminar({"ok": ok})


class Relogio:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _voz(tmp_path, motor=None, referencia=True):
    ref, txt = tmp_path / "ref.wav", tmp_path / "ref.txt"
    if referencia:
        ref.write_bytes(b"RIFF-referencia")
        txt.write_text("Oi, eu sou o teste.", encoding="utf-8")
    sistema, relogio = SistemaFalso(), Relogio()
    v = Voz(tmp_path / "cache", motor=motor, referencia=ref, referencia_texto=txt,
            ajustes={"sistema": "Eddy", "velocidade": 1.15, "seed": 7}, sistema=sistema, relogio=relogio)
    return v, sistema, relogio


# ---------------- texto e emoção ----------------

def test_para_fala_tira_emoji_e_baixa_caixa_alta():
    assert para_fala("tô de olho 👀") == "tô de olho"
    assert para_fala("ACORDE ÀS 4H. DURMA NO METAVERSO.") == "acorde às 4h. durma no metaverso."
    assert para_fala("bebe água. agora.") == "bebe água. agora."
    assert para_fala("  👀🔥  ") == ""
    assert para_fala(None) == ""


def test_emocao_vira_marca_e_velocidade():
    assert com_emocao("oi", "feliz") == ("[laughter] oi", 1.1)
    assert com_emocao("oi", "triste", 1.15) == ("[sigh] oi", round(1.15 * 0.85, 3))
    assert com_emocao("oi", "bravo") == ("[dissatisfaction-hnn] oi", 1.15)
    assert com_emocao("oi", "emocao-que-nao-existe") == ("oi", 1.0)
    assert com_emocao("oi", None, 1.15) == ("oi", 1.15)
    assert set(config.EMOTIONS) <= set(EMOCOES)          # toda emoção do pet tem um jeito de falar


# ---------------- voz do sistema ----------------

SAIDA_SAY = """\
Eddy (Inglês (EUA)) en_US    # Hello! My name is Eddy.
Eddy (Português (Brasil)) pt_BR    # Olá, meu nome é Eddy.
Joana               pt_PT    # Olá! Chamo-me Joana.
Luciana (Português (Brasil)) pt_BR    # Olá, meu nome é Luciana.
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="plataforma/macos.py só importa no macOS")
def test_escolher_voz_pega_a_do_portugues_do_brasil():
    from pestinha.plataforma import macos
    vozes = macos.ler_vozes(SAIDA_SAY)
    assert ("Joana", "pt_PT") in vozes
    assert macos.escolher_voz("Eddy", vozes) == "Eddy (Português (Brasil))"       # não a inglesa
    assert macos.escolher_voz("NaoExiste", vozes) == "Luciana (Português (Brasil))"
    assert macos.escolher_voz(None, vozes) == "Luciana (Português (Brasil))"
    assert macos.escolher_voz("Eddy", macos.ler_vozes("")) is None


def test_sem_voz_natural_usa_a_voz_do_sistema(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=None)
    v.dizer("bebe água 👀", "feliz")
    assert sistema.falas == [("bebe água", "Eddy")] and v.ultimo_motor == "sistema"


def test_sem_referencia_do_pet_usa_a_voz_do_sistema(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor, referencia=False)
    v.dizer("oi", "feliz")
    assert motor.pedidos == [] and sistema.falas == [("oi", "Eddy")]


def test_sem_voz_no_sistema_nao_faz_nada(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    sistema.TEM_VOZ = False
    v.dizer("oi")
    assert sistema.falas == [] and sistema.toques == []


# ---------------- voz natural ----------------

def test_voz_natural_pede_ao_motor_com_a_emocao_e_toca_quando_fica_pronta(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    v.dizer("ninguém lê o que eu escrevo", "triste")
    pedido, _ = motor.pedidos[0]
    assert pedido["texto"] == "[sigh] ninguém lê o que eu escrevo"
    assert pedido["velocidade"] == round(1.15 * 0.85, 3) and pedido["seed"] == 7
    assert pedido["referencia"] == str(tmp_path / "ref.wav") and pedido["referencia_texto"] == "Oi, eu sou o teste."
    assert sistema.toques == [] and sistema.falas == []          # nada toca antes de ficar pronto
    motor.responder()
    assert sistema.toques == [Path(pedido["saida"])] and v.ultimo_motor == "natural"


def test_segunda_vez_sai_do_cache_e_outra_emocao_e_outra_fala(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    v.dizer("oi", "feliz")
    motor.responder()
    v.dizer("oi", "feliz")
    assert len(motor.pedidos) == 1 and v.ultimo_motor == "cache"
    assert sistema.toques[0] == sistema.toques[1]
    v.dizer("oi", "bravo")
    assert len(motor.pedidos) == 2 and motor.pedidos[1][0]["saida"] != motor.pedidos[0][0]["saida"]


def test_trocar_a_referencia_invalida_o_cache(tmp_path):
    v, _, _ = _voz(tmp_path, motor=MotorFalso())
    antes = v.arquivo("oi", 1.0)
    (tmp_path / "ref.wav").write_bytes(b"RIFF-outra-voz")
    v2, _, _ = _voz(tmp_path, motor=MotorFalso(), referencia=False)       # reabrindo o pet
    assert v2.arquivo("oi", 1.0) != antes


def test_frase_nova_ganha_da_que_ainda_estava_sendo_gerada(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    v.dizer("primeira", "feliz")
    v.dizer("segunda", "feliz")
    motor.responder(0)
    assert sistema.toques == []                                  # a primeira não toca fora de hora
    assert Path(motor.pedidos[0][0]["saida"]).exists()          # mas fica no cache
    motor.responder(1)
    assert sistema.toques == [Path(motor.pedidos[1][0]["saida"])]


def test_fala_que_fica_pronta_tarde_demais_nao_toca(tmp_path):
    motor = MotorFalso()
    v, sistema, relogio = _voz(tmp_path, motor=motor)
    v.dizer("oi", "feliz")
    relogio.t += ATRASO_MAXIMO_S + 1
    motor.responder()
    assert sistema.toques == [] and sistema.falas == []


def test_motor_falhou_cai_na_voz_do_sistema(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    v.dizer("oi", "feliz")
    motor.responder(ok=False)
    assert sistema.falas == [("oi", "Eddy")]


def test_motor_parado_usa_a_voz_do_sistema(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso(rodando=False))
    v.dizer("oi", "feliz")
    assert sistema.falas == [("oi", "Eddy")]


def test_fechar_o_post_it_cancela_a_fala_que_estava_sendo_gerada(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    v.dizer("bebe água", "feliz")
    v.parar("outra frase")                     # fecharam outro post-it: nada muda
    v.parar("bebe água")                       # fecharam o dele, antes de ficar pronto
    motor.responder()
    assert sistema.toques == []


def test_fechar_o_post_it_cala_o_que_esta_tocando(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=None)
    v.dizer("bebe água")
    v.parar("outra frase")
    assert not sistema.processos[0].parado
    v.parar("bebe água")
    assert sistema.processos[0].parado


def test_ligar_e_desligar_so_mexem_no_motor_com_a_voz_natural(tmp_path):
    motor = MotorFalso()
    v, _, _ = _voz(tmp_path, motor=motor)
    v.ligar()
    v.desligar()
    assert motor.ligou == 1 and motor.desligou == 1
    sem = MotorFalso(instalado=False)
    v2, _, _ = _voz(tmp_path, motor=sem)
    v2.ligar()
    assert sem.ligou == 0


# ---------------- motor (processo de verdade, com um trabalhador falso) ----------------

TRABALHADOR_FALSO = textwrap.dedent("""
    import json, sys, time
    MORRER = False
    time.sleep(0.1)
    print(json.dumps({"evento": "pronto", "dispositivo": "falso", "segundos": 0.1}), flush=True)
    for linha in sys.stdin:
        if MORRER:
            sys.exit(3)
        p = json.loads(linha)
        open(p["saida"], "wb").write(b"RIFF")
        print(json.dumps({"id": p["id"], "ok": True, "texto": p["texto"]}), flush=True)
""")


def _esperar(condicao, tempo=5.0):
    fim = time.monotonic() + tempo
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return False


def _motor(tmp_path, morrer=False):
    script = tmp_path / "trabalhador.py"
    script.write_text(TRABALHADOR_FALSO.replace("MORRER = False", f"MORRER = {morrer}"), encoding="utf-8")
    return MotorVoz(tmp_path / "voz_natural", log_arquivo=tmp_path / "logs" / "voz.log", python=sys.executable,
                    trabalhador=script)


def test_motor_carrega_atende_os_pedidos_e_fecha(tmp_path):
    m = _motor(tmp_path)
    assert m.ligar() and m.estado == "carregando"
    respostas = []
    assert m.pedir({"texto": "oi", "saida": str(tmp_path / "a.wav")}, respostas.append)    # espera na fila
    assert _esperar(lambda: respostas)
    assert m.estado == "pronto" and m.dispositivo == "falso"
    assert respostas[0]["ok"] and respostas[0]["texto"] == "oi" and (tmp_path / "a.wav").exists()
    m.desligar()
    assert m.estado == "desligado" and not m.pedir({"texto": "x"}, respostas.append)


def test_motor_que_morre_responde_os_pendentes_com_erro(tmp_path):
    m = _motor(tmp_path, morrer=True)
    m.ligar()
    respostas = []
    m.pedir({"texto": "oi", "saida": str(tmp_path / "a.wav")}, respostas.append)
    assert _esperar(lambda: respostas)
    assert respostas == [{"ok": False, "erro": "o motor fechou"}]
    assert _esperar(lambda: m.estado == "falhou")


def test_motor_sem_instalacao_nao_liga(tmp_path):
    m = MotorVoz(tmp_path / "voz_natural")
    assert not m.instalado() and not m.ligar() and m.estado == "desligado"


def test_instalada_precisa_de_tudo(tmp_path):
    pasta = tmp_path / "voz_natural"
    assert not instalada(pasta)
    python_do_ambiente(pasta).parent.mkdir(parents=True)
    python_do_ambiente(pasta).write_text("")
    (pasta / "modelo").mkdir()
    (pasta / "modelo" / "model.safetensors").write_text("")
    assert not instalada(pasta)                    # sem instalado.json: o instalador não terminou
    (pasta / "instalado.json").write_text("{}")
    assert instalada(pasta)


# ---------------- trabalhador (sem o torch) ----------------

def _fala(segundos, volume=0.3):
    t = np.arange(int(segundos * trab.TAXA)) / trab.TAXA
    return (volume * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_trabalhador_reconhece_audio_mudo_e_cortado():
    silencio = np.zeros(trab.TAXA * 2, dtype=np.float32)
    meio = np.concatenate([_fala(0.5), np.zeros(trab.TAXA * 2, dtype=np.float32)])
    assert trab.fracao_de_fala(silencio) == 0.0
    assert trab.fracao_de_fala(meio) < trab.FALA_MINIMA
    assert trab.fracao_de_fala(_fala(2)) > 0.9


def test_trabalhador_corta_as_pontas_e_iguala_o_volume():
    audio = np.concatenate([np.zeros(trab.TAXA), _fala(1, 0.9), np.zeros(trab.TAXA)])
    pronto = trab.acabamento(audio)
    assert abs(len(pronto) / trab.TAXA - 1.2) < 0.1
    assert abs(np.abs(pronto).max() - trab.VOLUME) < 1e-3


def test_trabalhador_tenta_a_seed_seguinte_quando_sai_mudo():
    seeds = []

    def gerar(_texto, seed):
        seeds.append(seed)
        return _fala(1) if seed == 13 else np.zeros(trab.TAXA, dtype=np.float32)

    audio, tentativas = trab.sintetizar_com_tentativas(gerar, "oi", 11)
    assert seeds == [11, 12, 13] and tentativas == 3 and audio is not None
    nunca, n = trab.sintetizar_com_tentativas(lambda t, s: np.zeros(100, dtype=np.float32), "oi", 1, tentativas=2)
    assert nunca is None and n == 2


def test_trabalhador_responde_cada_pedido_sem_cair(tmp_path):
    salvos = []
    ok = trab.atender(json.dumps({"id": 4, "saida": str(tmp_path / "a.wav")}),
                      lambda p: (_fala(1), 2), lambda c, a: salvos.append(c))
    assert ok["id"] == 4 and ok["ok"] and ok["tentativas"] == 2 and salvos == [tmp_path / "a.wav"]
    mudo = trab.atender(json.dumps({"id": 5, "saida": "x"}), lambda p: (None, 5), lambda c, a: None)
    assert mudo == {"id": 5, "ok": False, "erro": "saiu mudo em 5 tentativas"}

    def quebra(_p):
        raise RuntimeError("MPS sem memória")

    erro = trab.atender(json.dumps({"id": 6, "saida": "x"}), quebra, lambda c, a: None)
    assert erro["id"] == 6 and not erro["ok"] and "MPS sem memória" in erro["erro"]
    assert trab.atender("isso não é json", quebra, lambda c, a: None) == {"ok": False, "erro": "pedido inválido"}


# ---------------- análise do computador ----------------

MAC_BOM = {"sistema": "darwin", "maquina": "arm64", "mac_arm64": True, "macos": "14.5", "memoria_gb": 24.0,
           "livre_gb": 200.0, "python": (3, 11), "congelado": False, "instalada": False}


def _estado(itens, nome):
    return next(e for n, e, _x in itens if n == nome)


def test_mac_apple_silicon_e_compativel():
    itens = inst.analisar(fatos=MAC_BOM)
    assert inst.compativel(itens) and all(e == "ok" for _n, e, _x in itens)


@pytest.mark.parametrize("mudanca, item", [
    ({"sistema": "win32"}, "Sistema"),
    ({"sistema": "linux"}, "Sistema"),
    ({"maquina": "x86_64", "mac_arm64": False}, "Processador"),
    ({"maquina": "x86_64", "mac_arm64": True}, "Processador"),       # Python Intel no Rosetta
    ({"macos": "12.7"}, "Versão do macOS"),
    ({"memoria_gb": 4.0}, "Memória"),
    ({"livre_gb": 2.0}, "Espaço em disco"),
    ({"congelado": True}, "Python"),
    ({"python": (3, 8)}, "Python"),
])
def test_o_que_impede_a_voz_natural(mudanca, item):
    itens = inst.analisar(fatos=dict(MAC_BOM, **mudanca))
    assert not inst.compativel(itens) and _estado(itens, item) == "falha"


def test_rosetta_explica_o_que_fazer():
    itens = inst.analisar(fatos=dict(MAC_BOM, maquina="x86_64", mac_arm64=True))
    assert "Rosetta" in next(x for n, _e, x in itens if n == "Processador")


def test_pouca_memoria_avisa_mas_deixa():
    itens = inst.analisar(fatos=dict(MAC_BOM, memoria_gb=8.0))
    assert inst.compativel(itens) and _estado(itens, "Memória") == "aviso"


def test_ja_instalada_nao_pede_espaco():
    assert inst.compativel(inst.analisar(fatos=dict(MAC_BOM, livre_gb=1.0, instalada=True)))


def test_coletar_fatos_deste_computador_nao_quebra(tmp_path):
    fatos = inst.coletar_fatos(tmp_path / "voz_natural")
    assert set(MAC_BOM) <= set(fatos) and fatos["livre_gb"] > 0
    inst.analisar(fatos=fatos)


def test_gb_com_virgula():
    assert inst.gb(4.5) == "4,5 GB"


# ---------------- instalação (sem internet: comandos falsos) ----------------

def _rodar_falso(pasta, chamadas, falhar=(), ja_tem_bibliotecas=False):
    def rodar(comando, escrever, ambiente=None):
        chamadas.append(comando)
        texto = " ".join(map(str, comando))
        if any(f in texto for f in falhar):
            return 1
        if "-m venv" in texto:
            python_do_ambiente(pasta).parent.mkdir(parents=True, exist_ok=True)
            python_do_ambiente(pasta).write_text("")
        elif "import torch, omnivoice" in texto:
            return 0 if ja_tem_bibliotecas else 1
        elif "snapshot_download" in texto:
            for nome in ("model.safetensors", "audio_tokenizer/model.safetensors"):
                arq = pasta / "modelo" / nome
                arq.parent.mkdir(parents=True, exist_ok=True)
                with open(arq, "wb") as f:
                    f.truncate(101 * 1024 ** 2)
        elif "--teste" in texto:
            escrever(json.dumps({"ok": True, "dispositivo": "mps"}))
        return 0
    return rodar


def test_instalar_faz_os_quatro_passos_e_marca_instalada(tmp_path):
    pasta, chamadas = tmp_path / "voz_natural", []
    assert inst.instalar(pasta, lambda _l: None, rodar=_rodar_falso(pasta, chamadas))
    texto = [" ".join(map(str, c)) for c in chamadas]
    assert any("-m venv" in t for t in texto)
    assert any("torch==2.8.0" in t and "omnivoice==0.2.1" in t for t in texto)
    assert any(inst.MODELO_REVISAO in t for t in texto)
    assert any("--teste" in t for t in texto)
    assert instalada(pasta) and json.loads((pasta / "instalado.json").read_text())["dispositivo"] == "mps"


def test_instalar_de_novo_pula_o_que_ja_esta_pronto(tmp_path):
    pasta = tmp_path / "voz_natural"
    inst.instalar(pasta, lambda _l: None, rodar=_rodar_falso(pasta, []))
    chamadas = []
    assert inst.instalar(pasta, lambda _l: None, rodar=_rodar_falso(pasta, chamadas, ja_tem_bibliotecas=True))
    texto = " ".join(" ".join(map(str, c)) for c in chamadas)
    assert "-m venv" not in texto and "pip install" not in texto and "snapshot_download" not in texto


def test_download_que_falha_nao_marca_instalada(tmp_path):
    pasta, linhas = tmp_path / "voz_natural", []
    assert not inst.instalar(pasta, linhas.append, rodar=_rodar_falso(pasta, [], falhar=("snapshot_download",)))
    assert not instalada(pasta) and any("continua de onde parou" in linha for linha in linhas)


def test_remover_apaga_a_pasta(tmp_path):
    pasta = tmp_path / "voz_natural"
    inst.instalar(pasta, lambda _l: None, rodar=_rodar_falso(pasta, []))
    inst.remover(pasta)
    assert not pasta.exists()
    inst.remover(pasta)                            # já removida: não quebra


# ---------------- configuração, caminhos e as vozes que vêm com o Pestinha ----------------

def test_voz_vem_desligada_e_aparece_nas_configuracoes():
    assert config.DEFAULT_PERMISSIONS["voz"] is False
    chaves = [k for _titulo, itens in config.PERMISSION_GROUPS for k, _r, _d in itens]
    assert "voz" in chaves


def test_pet_json_aceita_so_ajustes_de_voz_validos():
    assert config._pet_valido({"voz": {"sistema": "Eddy", "velocidade": 1.15, "seed": 11}})["voz"] == {
        "sistema": "Eddy", "velocidade": 1.15, "seed": 11}
    ruim = config._pet_valido({"voz": {"sistema": 3, "velocidade": 9.0, "seed": -1, "outra": "x"}})
    assert ruim["voz"] == {}
    assert "voz" not in config._pet_valido({"voz": "Eddy"})


def test_voz_natural_fica_fora_dos_seus_dados(tmp_path):
    paths = Paths(root=tmp_path)
    assert paths.voz_natural == tmp_path / "voz_natural"
    assert paths.memory not in paths.voz_natural.parents      # "apagar todos os dados" não apaga o download
    assert paths.memory in paths.voz("bryan").parents          # o cache das falas é dado seu
    assert paths.conteudo("bryan").voz_referencia == tmp_path / "pets" / "bryan" / "voz" / "referencia.wav"


@pytest.mark.parametrize("pet", ["bryan", "jorge"])
def test_os_pets_vem_com_a_voz_deles(pet):
    conteudo = Paths(root=RAIZ).conteudo(pet)
    with wave.open(str(conteudo.voz_referencia)) as w:
        segundos = w.getnframes() / w.getframerate()
        assert w.getnchannels() == 1 and 3.0 <= segundos <= 10.0     # o que a clonagem pede
    assert len(conteudo.voz_referencia_texto.read_text(encoding="utf-8").split()) >= 5
    voz = config.load_pet(Paths(root=RAIZ), pet)["voz"]
    assert voz["sistema"] and voz["seed"] >= 0


# ---------------- tela ----------------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_tela_libera_o_download_so_quando_e_compativel(qapp, tmp_path):
    from pestinha.ui.voz_natural import VozNaturalDialog
    paths = Paths(root=tmp_path)
    bom = VozNaturalDialog(paths, analisar=lambda: inst.analisar(fatos=MAC_BOM))
    assert bom.instalar_btn.isEnabled() and "Compatível" in bom.status.text()
    ruim = VozNaturalDialog(paths, analisar=lambda: inst.analisar(fatos=dict(MAC_BOM, sistema="win32")))
    assert not ruim.instalar_btn.isEnabled() and "não aguenta" in ruim.status.text()


def test_tela_instala_mostrando_o_andamento(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from pestinha.ui.voz_natural import VozNaturalDialog
    paths = Paths(root=tmp_path)
    falso = tmp_path / "instalador_falso.py"
    python = python_do_ambiente(paths.voz_natural)            # ambiente/bin/python, ou ambiente\Scripts\python.exe no Windows
    falso.write_text(textwrap.dedent(f"""
        from pathlib import Path
        pasta, python = Path({str(paths.voz_natural)!r}), Path({str(python)!r})
        print("[1/4] Ambiente", flush=True)
        python.parent.mkdir(parents=True)
        python.write_text("")
        (pasta / "modelo").mkdir()
        (pasta / "modelo" / "model.safetensors").write_text("")
        (pasta / "instalado.json").write_text("{{}}")
        print("Pronto!", flush=True)
    """), encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d = VozNaturalDialog(paths, analisar=lambda: inst.analisar(fatos=MAC_BOM), comando=[sys.executable, str(falso)])
    mudou = []
    d.mudou.connect(lambda: mudou.append(True))
    d.instalar()
    assert d.processo.waitForFinished(10000)
    qapp.processEvents()
    assert mudou and "Pronto!" in d.saida.toPlainText() and "Instalada" in d.status.text()
    assert d.instalar_btn.isHidden()


def test_tela_de_configuracoes_tem_o_botao_da_voz_natural(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from pestinha import plataforma
    from pestinha.ui.ui import SettingsDialog
    monkeypatch.setattr(plataforma, "TEM_VOZ", True)
    d = SettingsDialog(dict(config.DEFAULT_PERMISSIONS), Paths(root=tmp_path), first_run=False)
    assert any(b.text() == "Voz natural..." for b in d.findChildren(QPushButton))
    assert "não instalada" in d.voz_status.text()


def test_sem_voz_no_sistema_as_telas_nao_prometem_a_voz_do_sistema(qapp, tmp_path, monkeypatch):
    from pestinha import plataforma
    from pestinha.ui.ui import SettingsDialog
    from pestinha.ui.voz_natural import VozNaturalDialog
    monkeypatch.setattr(plataforma, "TEM_VOZ", False)                 # Windows e Linux, por enquanto
    paths = Paths(root=tmp_path)
    d = SettingsDialog(dict(config.DEFAULT_PERMISSIONS), paths, first_run=False)
    assert "ainda não fala" in d.voz_status.text() and not d.boxes["voz"].isEnabled()
    v = VozNaturalDialog(paths, analisar=lambda: inst.analisar(fatos=dict(MAC_BOM, sistema="win32")))
    assert "ainda não fala" in v.status.text() and "voz do sistema" not in v.status.text()
