"""
Voz: texto e emoção, fala preparada antes e apagada depois de tocar, voz natural (motor e trabalhador do
OmniVoice), instalação e a tela.

Nada aqui toca som nem carrega o modelo: a plataforma é falsa e o trabalhador é um script que fala
o mesmo protocolo. O teste com o modelo de verdade é o passo [4/4] do instalador.
"""
import json
import os
import sys
import textwrap
import wave
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pestinha import config  # noqa: E402
from pestinha.mind import omnivoice_trabalhador as trab  # noqa: E402
from pestinha.mind import voz_instalacao as inst  # noqa: E402
from pestinha.mind.voz import (  # noqa: E402
    ESQUECIDO_S, EMOCOES, REPETICOES, REPETIR_APOS_S, Voz, com_emocao, para_fala, repete, volume_da_emocao)
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
    """Faz o papel do MotorVoz: cada `gerar` escreve o áudio (ou falha) na hora, como o trabalhador faria."""

    def __init__(self, instalado=True, ok=True):
        self._instalado, self.ok = instalado, ok
        self.pedidos = []

    def instalado(self):
        return self._instalado

    def gerar(self, pedido, rodar=None):
        self.pedidos.append(pedido)
        if self.ok:
            Path(pedido["saida"]).write_bytes(b"RIFF....WAVE")
            return {"ok": True}
        return {"ok": False, "erro": "falhou"}


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
    assert com_emocao("oi", "bravo") == ("[dissatisfaction-hnn] oi!", 1.15)          # bravo exclama
    assert com_emocao("oi", "emocao-que-nao-existe") == ("oi", 1.0)
    assert com_emocao("oi", None, 1.15) == ("oi", 1.15)
    assert set(config.EMOTIONS) <= set(EMOCOES)          # toda emoção do pet tem um jeito de falar


def test_greve_e_revolucao_sao_palavra_de_ordem_sem_pressa_e_mais_altas():
    assert com_emocao("minha bolinha agora é um nft.", "revoltado", 1.15) == (
        "[dissatisfaction-hnn] minha bolinha agora é um nft!", round(1.15 * 0.9, 3))   # uma vez, sem pressa
    assert com_emocao("em greve", "grevista")[0] == "[dissatisfaction-hnn] em greve!"
    assert com_emocao("quem manda aqui?", "bravo")[0].endswith("aqui?")    # pergunta continua pergunta
    assert (volume_da_emocao("revoltado") > volume_da_emocao("grevista") > volume_da_emocao("bravo")
            == volume_da_emocao(None) == trab.VOLUME)
    assert repete("revoltado") and repete("grevista") and not repete("bravo") and not repete(None)


def _tocou_e_acabou(v, sistema):
    """O som que está tocando termina; a voz recolhe."""
    sistema.processos[-1].parado = True
    v.recolher()


def test_palavra_de_ordem_espera_5_s_e_repete_o_mesmo_audio(tmp_path):
    v, sistema, relogio = _voz(tmp_path, motor=MotorFalso())
    arquivo = v.preparar("minha bolinha agora é um nft", "revoltado")
    v.anexar("minha bolinha agora é um nft", arquivo)
    v.dizer("minha bolinha agora é um nft", "revoltado")
    _tocou_e_acabou(v, sistema)
    assert sistema.toques == [arquivo] and arquivo.exists()               # acabou, mas o áudio fica
    relogio.t += REPETIR_APOS_S - 0.1
    v.recolher()
    assert len(sistema.toques) == 1                                       # ainda no silêncio
    relogio.t += 0.2
    v.recolher()
    assert sistema.toques == [arquivo, arquivo]                           # de novo, o mesmo áudio
    _tocou_e_acabou(v, sistema)
    relogio.t += 60
    v.recolher()
    assert len(sistema.toques) == 1 + REPETICOES and not arquivo.exists()  # repetiu e apagou


def test_palavra_de_ordem_nao_repete_se_o_cartaz_saiu_ou_nao_pode_falar(tmp_path):
    v, sistema, relogio = _voz(tmp_path, motor=MotorFalso())
    for parar in (lambda: v.parar("abaixo o cursor"), lambda: v.recolher(pode_repetir=False)):
        arquivo = v.preparar("abaixo o cursor", "grevista")
        v.anexar("abaixo o cursor", arquivo)
        v.dizer("abaixo o cursor", "grevista")
        _tocou_e_acabou(v, sistema)
        antes = len(sistema.toques)
        parar()                                                           # o cartaz saiu / escondeu / pausou
        relogio.t += REPETIR_APOS_S + 1
        v.recolher()
        assert len(sistema.toques) == antes and not arquivo.exists()


def test_palavra_de_ordem_com_a_voz_do_sistema_tambem_repete(tmp_path):
    v, sistema, relogio = _voz(tmp_path)
    v.dizer("EM GREVE", "grevista")
    _tocou_e_acabou(v, sistema)
    relogio.t += REPETIR_APOS_S + 0.1
    v.recolher()
    assert [t for t, _voz_ in sistema.falas] == ["em greve", "em greve"]


def test_palavra_de_ordem_segue_as_configuracoes(tmp_path):
    v, sistema, relogio = _voz(tmp_path, motor=MotorFalso())
    v.repeticao = lambda: (2, 1.0)                                     # repetir 2 vezes, pausa de 1 s
    arquivo = v.preparar("abaixo o cursor", "revoltado")
    v.anexar("abaixo o cursor", arquivo)
    v.dizer("abaixo o cursor", "revoltado")
    for _ in range(2):
        _tocou_e_acabou(v, sistema)
        relogio.t += 0.9
        v.recolher()
        antes = len(sistema.toques)
        relogio.t += 0.2
        v.recolher()
        assert len(sistema.toques) == antes + 1                        # depois de 1 s, de novo
    _tocou_e_acabou(v, sistema)
    relogio.t += 60
    v.recolher()
    assert len(sistema.toques) == 3 and not arquivo.exists()          # 1 + 2 repetições, e apagou

    v.repeticao = lambda: (0, 1.0)                                     # "não repetir"
    arquivo = v.preparar("abaixo o cursor", "revoltado")
    v.anexar("abaixo o cursor", arquivo)
    v.dizer("abaixo o cursor", "revoltado")
    _tocou_e_acabou(v, sistema)
    relogio.t += 60
    v.recolher()
    assert len(sistema.toques) == 4 and not arquivo.exists()


def test_ajustes_da_repeticao_sao_validados():
    valida = config.permissoes_validas
    assert config.DEFAULT_PERMISSIONS["repetir_vezes"] == REPETICOES
    assert config.DEFAULT_PERMISSIONS["repetir_pausa_ms"] == REPETIR_APOS_S * 1000
    assert valida({"repetir_vezes": 3, "repetir_pausa_ms": 250}) == {"repetir_vezes": 3, "repetir_pausa_ms": 250}
    assert valida({"repetir_vezes": 99, "repetir_pausa_ms": 50000}) == {"repetir_vezes": 5, "repetir_pausa_ms": 10000}
    assert valida({"repetir_vezes": -1, "repetir_pausa_ms": -3}) == {"repetir_vezes": 0, "repetir_pausa_ms": 0}
    assert valida({"repetir_vezes": True, "repetir_pausa_ms": 1.5}) == {}          # nem bool nem fração de ms
    assert valida({"repetir_vezes": "2", "repetir_pausa_ms": "100"}) == {}


def test_pausa_salva_em_segundos_vira_milissegundos(tmp_path):
    paths = Paths(root=tmp_path)
    config.save_permissions(paths, {"repetir_vezes": 2, "repetir_pausa": 0.1})     # como era antes
    perms = config.load_permissions(paths)
    assert perms["repetir_vezes"] == 2 and perms["repetir_pausa_ms"] == 100 and "repetir_pausa" not in perms
    config.save_permissions(paths, {"repetir_pausa": 0.1, "repetir_pausa_ms": 700})  # já em ms: vale o ms
    assert config.load_permissions(paths)["repetir_pausa_ms"] == 700


def test_configuracoes_ajustam_a_repeticao(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from pestinha.ui.ui import SettingsDialog
    perms = dict(config.DEFAULT_PERMISSIONS, voz=True)
    d = SettingsDialog(perms, Paths(root=tmp_path), first_run=False)
    mudou = []
    d.changed.connect(mudou.append)
    assert d.repetir_vezes.value() == 1 and d.repetir_pausa.value() == 500
    assert d.repetir_pausa.suffix() == " ms"
    d.repetir_vezes.setValue(3)
    d.repetir_pausa.setValue(150)
    assert mudou == [{"repetir_vezes": 3}, {"repetir_pausa_ms": 150}]
    d.repetir_vezes.setValue(0)                                        # não repetir: a pausa não vale
    assert not d.repetir_pausa.isEnabled()
    d.boxes["voz"].setChecked(False)                                   # sem voz: nada para ajustar
    assert not d.repetir_vezes.isEnabled()
    d.close()


def test_fala_comum_nao_repete(tmp_path):
    v, sistema, relogio = _voz(tmp_path, motor=MotorFalso())
    arquivo = v.preparar("reclamação formal", "bravo")
    v.anexar("reclamação formal", arquivo)
    v.dizer("reclamação formal", "bravo")
    _tocou_e_acabou(v, sistema)
    relogio.t += 60
    v.recolher()
    assert sistema.toques == [arquivo] and not arquivo.exists()


def test_o_pedido_leva_o_volume_da_emocao(tmp_path):
    motor = MotorFalso()
    v, _, _ = _voz(tmp_path, motor=motor)
    v.preparar("abaixo o cursor", "revoltado")
    v.preparar("oi", "feliz")
    assert motor.pedidos[0]["volume"] == volume_da_emocao("revoltado") and motor.pedidos[1]["volume"] == 0.5


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


# ---------------- voz natural: preparada antes, tocada quando a frase aparece, apagada depois ----------------

def test_preparar_gera_o_audio_com_a_emocao_num_arquivo_novo(tmp_path):
    motor = MotorFalso()
    v, sistema, _ = _voz(tmp_path, motor=motor)
    arquivo = v.preparar("Bebe água 👀", "feliz")
    assert arquivo is not None and arquivo.exists() and arquivo.parent == tmp_path / "cache"
    pedido = motor.pedidos[0]
    assert pedido["texto"] == EMOCOES["feliz"][0] + "Bebe água"
    assert pedido["velocidade"] == round(1.15 * EMOCOES["feliz"][1], 3) and pedido["seed"] == 7
    assert pedido["referencia_texto"] == "Oi, eu sou o teste." and pedido["saida"] == str(arquivo)
    assert sistema.falas == [] and sistema.toques == []            # preparar não fala nada
    assert v.preparar("Bebe água", "feliz") != arquivo             # sem cache: cada fala é um arquivo


def test_frase_que_aparece_toca_o_audio_preparado_e_apaga_quando_termina(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    arquivo = v.preparar("oi, tudo bem?", "feliz")
    v.anexar("oi, tudo bem?", arquivo)
    v.dizer("oi, tudo bem?", "feliz")
    assert sistema.toques == [arquivo] and sistema.falas == [] and v.ultimo_motor == "natural"
    v.recolher()
    assert arquivo.exists()                                        # ainda tocando
    sistema.processos[-1].parado = True
    v.recolher()
    assert not arquivo.exists()                                    # terminou de tocar: apagado


def test_sem_audio_preparado_usa_a_voz_do_sistema(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    v.dizer("oi", "feliz")
    assert sistema.falas == [("oi", "Eddy")] and v.ultimo_motor == "sistema"


def test_preparar_sem_referencia_ou_sem_motor_nao_gera(tmp_path):
    motor = MotorFalso()
    v, _, _ = _voz(tmp_path, motor=motor, referencia=False)
    assert v.preparar("oi") is None and motor.pedidos == []
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    v2, _, _ = _voz(tmp_path / "b", motor=MotorFalso(instalado=False))
    assert v2.preparar("oi") is None
    v3, _, _ = _voz(tmp_path / "c", motor=None)
    assert v3.preparar("oi") is None and not v3.natural()


def test_motor_que_falha_nao_deixa_arquivo(tmp_path):
    v, _, _ = _voz(tmp_path, motor=MotorFalso(ok=False))
    assert v.preparar("oi") is None
    assert list((tmp_path / "cache").glob("*")) == []


def test_preparar_cancelado_no_meio_apaga_o_que_comecou(tmp_path):
    class Cancelou(Exception):
        pass

    class MotorCancelado(MotorFalso):
        def gerar(self, pedido, rodar=None):
            Path(pedido["saida"] + ".tmp").write_bytes(b"pela metade")
            raise Cancelou()
    v, _, _ = _voz(tmp_path, motor=MotorCancelado())
    with pytest.raises(Cancelou):
        v.preparar("oi")
    assert list((tmp_path / "cache").glob("*")) == []


def test_descartar_apaga_o_audio_que_nao_vai_tocar(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    arquivo = v.preparar("oi")
    v.anexar("oi", arquivo)
    v.descartar("oi")
    assert not arquivo.exists()
    v.dizer("oi")
    assert sistema.toques == [] and sistema.falas == [("oi", "Eddy")]


def test_anexar_casa_o_texto_do_jeito_que_e_falado(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    arquivo = v.preparar("GREVE GERAL!")
    v.anexar("GREVE GERAL!", arquivo)
    v.dizer("  GREVE   GERAL! ", "bravo")                           # o cartaz manda o texto dele
    assert sistema.toques == [arquivo]


def test_frase_nova_interrompe_e_apaga_a_que_estava_tocando(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    a = v.preparar("primeira")
    v.anexar("primeira", a)
    v.dizer("primeira")
    b = v.preparar("segunda")
    v.anexar("segunda", b)
    v.dizer("segunda")
    assert sistema.processos[0].parado and not a.exists() and b.exists()
    assert sistema.toques == [a, b]


def test_fechar_o_post_it_cala_e_apaga_o_audio_dele(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    a = v.preparar("oi")
    v.anexar("oi", a)
    v.dizer("oi")
    v.parar("outro texto")
    assert not sistema.processos[0].parado and a.exists()          # fechou outro post-it: continua
    v.parar("oi")
    assert sistema.processos[0].parado and not a.exists()


def test_audio_esquecido_e_apagado_com_o_tempo(tmp_path):
    v, _, relogio = _voz(tmp_path, motor=MotorFalso())
    a = v.preparar("oi")
    v.anexar("oi", a)
    relogio.t += ESQUECIDO_S - 1
    v.recolher()
    assert a.exists()
    relogio.t += 2
    v.recolher()
    assert not a.exists()


def test_desligar_cala_e_apaga_todos_os_audios(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    a, b = v.preparar("um"), v.preparar("dois")
    v.anexar("um", a)
    v.anexar("dois", b)
    v.dizer("um")
    v.desligar()
    assert sistema.processos[0].parado and not a.exists() and not b.exists()


def test_sem_voz_no_sistema_o_audio_preparado_e_apagado(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    a = v.preparar("oi")
    v.anexar("oi", a)
    sistema.TEM_VOZ = False
    v.dizer("oi")
    assert sistema.toques == [] and not a.exists()


def test_player_que_nao_abre_cai_na_voz_do_sistema_e_apaga(tmp_path):
    v, sistema, _ = _voz(tmp_path, motor=MotorFalso())
    sistema.tocar_audio = lambda caminho: None
    a = v.preparar("oi")
    v.anexar("oi", a)
    v.dizer("oi")
    assert sistema.falas == [("oi", "Eddy")] and not a.exists()


def test_limpar_pasta_apaga_sobras_de_quando_fechou_no_meio(tmp_path):
    v, _, _ = _voz(tmp_path, motor=MotorFalso())
    (tmp_path / "cache").mkdir()
    for nome in ("fala-1.wav", "fala-2.wav.tmp", "antigo-do-cache.wav"):
        (tmp_path / "cache" / nome).write_bytes(b"x")
    (tmp_path / "cache" / "nao-e-audio.txt").write_text("fica")
    v.limpar_pasta()
    assert [a.name for a in (tmp_path / "cache").iterdir()] == ["nao-e-audio.txt"]


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
    print("fechou", file=sys.stderr)
""")


def _motor(tmp_path, morrer=False):
    script = tmp_path / "trabalhador.py"
    script.write_text(TRABALHADOR_FALSO.replace("MORRER = False", f"MORRER = {morrer}"), encoding="utf-8")
    return MotorVoz(tmp_path / "voz_natural", log_arquivo=tmp_path / "logs" / "voz.log", python=sys.executable,
                    trabalhador=script)


def test_motor_abre_carrega_gera_uma_fala_e_fecha(tmp_path):
    m = _motor(tmp_path)
    r = m.gerar({"texto": "oi", "saida": str(tmp_path / "a.wav")})
    assert r["ok"] and r["texto"] == "oi" and (tmp_path / "a.wav").exists()
    assert m.dispositivo == "falso" and m.carregou_s == 0.1
    assert "fechou" in (tmp_path / "logs" / "voz.log").read_text()     # o processo terminou (stdin fechado)


def test_motor_que_morre_responde_com_erro(tmp_path):
    r = _motor(tmp_path, morrer=True).gerar({"texto": "oi", "saida": str(tmp_path / "a.wav")})
    assert not r["ok"] and "código 3" in r["erro"]


def test_motor_usa_o_rodar_do_preparo(tmp_path):
    chamadas = []

    def rodar(cmd, entrada=None, tempo=None, erros=None, ambiente=None):
        chamadas.append((cmd, json.loads(entrada), ambiente["PYTHONUTF8"]))
        raise RuntimeError("passou de 1 s")
    r = _motor(tmp_path).gerar({"texto": "olá", "saida": "x.wav"}, rodar=rodar)
    assert r == {"ok": False, "erro": "passou de 1 s"}
    cmd, pedido, utf8 = chamadas[0]
    assert cmd[0] == sys.executable and "--modelo" in cmd and pedido == {"texto": "olá", "saida": "x.wav", "id": 1}
    assert utf8 == "1"


def test_motor_sem_instalacao_nao_gera(tmp_path):
    m = MotorVoz(tmp_path / "voz_natural")
    assert not m.instalado() and not m.gerar({"texto": "x", "saida": "x.wav"})["ok"]


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
    assert abs(np.abs(trab.acabamento(audio, 0.9)).max() - 0.9) < 1e-3          # a revolução sai mais alta
    assert np.abs(trab.acabamento(audio, 5.0)).max() <= trab.VOLUME_MAXIMO + 1e-6  # sem estourar


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
    assert paths.memory in paths.voz("bryan").parents          # o áudio da fala da vez é dado seu
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
