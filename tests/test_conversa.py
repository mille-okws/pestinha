"""
Conversa em texto (opcional): limites, provedor simulado, janela sem travar e integração com o app.

Tudo com Qt offscreen e numa pasta temporária. Nenhum modelo de verdade é chamado.
"""

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.ajustes import CONVERSA_MAX_ENTRADA, CONVERSA_MAX_RESPOSTA  # noqa: E402
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.core import conversa  # noqa: E402
from pestinha.core.conversa import (  # noqa: E402
    Cancelado,
    ModeloIndisponivel,
    Pedido,
    Provedor,
    ProvedorSimulado,
    RespostaInvalida,
    SemConexao,
)
from pestinha.paths import Paths  # noqa: E402
from pestinha.settings_store import SettingsStore  # noqa: E402
from pestinha.ui.conversa import JanelaConversa  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def buddy(qapp, tmp_path):
    paths = Paths(root=tmp_path)
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))
    app = PestinhaApp(store, paths)
    yield app
    app.fechar_conversa()
    app.mischief.clear()
    app.tray.icon.hide()


def esperar(qapp, condicao, segundos=5.0):
    fim = time.monotonic() + segundos
    while not condicao():
        if time.monotonic() > fim:
            raise AssertionError("a condição não aconteceu a tempo")
        qapp.processEvents()
        time.sleep(0.01)


def janela(qapp, provedor=None, tempo_max=5.0, emocao="feliz"):
    return JanelaConversa(provedor or ProvedorSimulado(atraso=(0.0, 0.0)), "Bryan", lambda: emocao, tempo_max)


# ---------------- regras puras ----------------

def test_entrada_vazia_ou_longa_e_recusada():
    for ruim in ("", "   ", "\x00\x07", None, 42):
        with pytest.raises(ValueError):
            conversa.limpar_entrada(ruim)
    with pytest.raises(ValueError):
        conversa.limpar_entrada("a" * (CONVERSA_MAX_ENTRADA + 1))
    assert conversa.limpar_entrada("a" * CONVERSA_MAX_ENTRADA) == "a" * CONVERSA_MAX_ENTRADA
    assert conversa.limpar_entrada("  oi\x00 pet\x1b  ") == "oi pet"


def test_pedido_leva_so_o_contexto_minimo():
    pedido = conversa.montar_pedido("oi", "Bryan", "feliz")
    assert pedido == Pedido(texto="oi", nome_pet="Bryan", emocao="feliz")
    assert set(vars(pedido)) == {"texto", "nome_pet", "emocao"}


def test_resposta_invalida_ou_longa():
    for ruim in (None, 3, b"bytes", "", "   ", "\x00\x01"):
        with pytest.raises(RespostaInvalida):
            conversa.validar_resposta(ruim)
    longa = conversa.validar_resposta("x" * (CONVERSA_MAX_RESPOSTA + 50))
    assert len(longa) == CONVERSA_MAX_RESPOSTA and longa.endswith("…")
    assert conversa.validar_resposta(" oi\x07 ") == "oi"


def test_simulado_responde_e_simula_falhas():
    sim = ProvedorSimulado(atraso=(0.0, 0.0))
    livre = threading.Event()
    assert sim.responder(Pedido("oi", "Bryan", "triste"), livre) in ProvedorSimulado.FRASES["triste"]
    with pytest.raises(ModeloIndisponivel):
        sim.responder(Pedido("/erro", "Bryan", "feliz"), livre)
    with pytest.raises(SemConexao):
        sim.responder(Pedido("/semrede", "Bryan", "feliz"), livre)
    cancelado = threading.Event()
    cancelado.set()
    with pytest.raises(Cancelado):
        sim.responder(Pedido("/lento", "Bryan", "feliz"), cancelado)
    assert sim.envia_para_fora is False


def test_provedor_desconhecido_vira_simulado():
    assert isinstance(conversa.criar_provedor("nao-existe"), ProvedorSimulado)


# ---------------- janela ----------------

def test_janela_responde_sem_travar(qapp):
    j = janela(qapp)
    j.entrada.setText("oi, tudo bem")
    j.enviar()
    assert j.ocupado and not j.botao_enviar.isEnabled()     # a interface volta na hora; a resposta vem depois
    esperar(qapp, lambda: not j.ocupado)
    texto = j.historico.toPlainText()
    assert "Você: oi, tudo bem" in texto and "Bryan:" in texto
    j.close()


def test_entrada_ruim_nao_envia(qapp):
    j = janela(qapp)
    j.entrada.setText("   ")
    j.enviar()
    assert not j.ocupado and "Escreva" in j.status.text()
    j.close()


def test_tempo_maximo_desiste_e_ignora_resposta_atrasada(qapp):
    j = janela(qapp, tempo_max=0.2)
    j.entrada.setText("/lento")
    j.enviar()
    esperar(qapp, lambda: not j.ocupado)
    assert "Demorou demais" in j.status.text()
    j._terminou(1, "chegou tarde", None)                     # resposta atrasada do pedido 1
    assert "chegou tarde" not in j.historico.toPlainText()
    j.close()


def test_cancelar_resposta(qapp):
    j = janela(qapp)
    j.entrada.setText("/lento")
    j.enviar()
    evento = j._pendente[1]
    j.cancelar()
    assert evento.is_set() and not j.ocupado and j.botao_enviar.isEnabled()
    assert j.status.text() == "Resposta cancelada."
    j.close()


@pytest.mark.parametrize("comando, mensagem", [
    ("/invalido", RespostaInvalida.mensagem),
    ("/erro", ModeloIndisponivel.mensagem),
    ("/semrede", SemConexao.mensagem),
])
def test_falhas_viram_mensagem(qapp, comando, mensagem):
    j = janela(qapp)
    j.entrada.setText(comando)
    j.enviar()
    esperar(qapp, lambda: not j.ocupado)
    assert j.status.text() == mensagem
    j.close()


def test_provedor_com_defeito_nao_derruba(qapp):
    class Quebrado(Provedor):
        nome = "quebrado"

        def responder(self, pedido, cancelado):
            raise KeyError("defeito")

    j = janela(qapp, provedor=Quebrado())
    j.entrada.setText("oi")
    j.enviar()
    esperar(qapp, lambda: not j.ocupado)
    assert j.status.text() == conversa.ErroConversa.mensagem
    j.close()


def test_fechar_cancela_e_apaga(qapp):
    j = janela(qapp)
    fechou = []
    j.fechada.connect(lambda: fechou.append(True))
    j.entrada.setText("/lento")
    j.enviar()
    evento = j._pendente[1]
    j.close()
    assert evento.is_set() and fechou == [True]


def test_aviso_diz_se_o_texto_sai_do_computador(qapp):
    class Remoto(ProvedorSimulado):
        envia_para_fora = True

    local = janela(qapp)
    remoto = janela(qapp, provedor=Remoto())
    assert "Nada sai do computador" in local._texto_aviso()
    assert "SAEM do computador" in remoto._texto_aviso()
    local.close()
    remoto.close()


# ---------------- integração com o app ----------------

def test_comeca_desligada(buddy):
    assert config.DEFAULT_PERMISSIONS["conversa"] is False
    buddy.abrir_conversa()
    assert buddy.conversa is None


def test_ligar_abrir_e_desligar_fecha(buddy):
    buddy.apply_perms({"conversa": True})
    buddy.abrir_conversa()
    assert isinstance(buddy.conversa, JanelaConversa)
    buddy.apply_perms({"conversa": False})
    assert buddy.conversa is None


def test_panico_fecha_a_conversa(buddy):
    buddy.apply_perms({"conversa": True})
    buddy.abrir_conversa()
    buddy.panic()
    assert buddy.conversa is None


def test_conversa_nao_grava_nada_nem_mexe_no_cerebro(buddy, qapp, tmp_path):
    buddy.apply_perms({"conversa": True})
    w_antes = buddy.brain.W.copy()
    aprendido_antes = buddy.brain.learned.copy()
    buddy.abrir_conversa()
    j = buddy.conversa
    j.provedor = ProvedorSimulado(atraso=(0.0, 0.0))
    j.entrada.setText("segredo-xyz-123")
    j.enviar()
    esperar(qapp, lambda: not j.ocupado)
    buddy.save()
    buddy.fechar_conversa()
    assert (buddy.brain.W == w_antes).all() and (buddy.brain.learned == aprendido_antes).all()
    for arquivo in tmp_path.rglob("*"):
        if arquivo.is_file():
            assert b"segredo-xyz-123" not in arquivo.read_bytes(), arquivo
