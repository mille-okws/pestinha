"""Painéis do menu (monitor neural e painel de protesto): abrir à mão deve manter o painel na tela."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.paths import Paths  # noqa: E402
from pestinha.settings_store import SettingsStore  # noqa: E402


@pytest.fixture
def pet_app(tmp_path):
    app_qt = QApplication.instance() or QApplication([])
    app_qt.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))           # modo teste desligado (padrão)
    app = PestinhaApp(store, paths)
    yield app
    app.floats.hidden_by_tray = True
    for w in list(app.floats.windows.values()):
        w.close()


def test_painel_aberto_no_menu_fica_na_tela_fora_do_modo_teste(pet_app):
    pet_app.floats.open("neural")
    pet_app.floats.sync(pet_app.floats_allowed(), pet_app.floats_base())
    assert pet_app.floats.window("neural").isVisible()


def test_so_a_cena_fica_na_frente_os_paineis_ficam_normais(pet_app):
    from PySide6.QtCore import Qt
    for chave in ("neural", "greve"):
        painel = pet_app.floats.window(chave)
        assert not painel.na_frente and not painel.windowFlags() & Qt.WindowStaysOnTopHint
    assert pet_app.mesa.caderno.windowFlags() & Qt.WindowStaysOnTopHint      # o notebook fica com o pet
    assert pet_app.pet.windowFlags() & Qt.WindowStaysOnTopHint


def test_menu_traz_o_painel_para_a_frente_e_tem_o_fechar(pet_app, monkeypatch):
    from PySide6.QtWidgets import QMenu
    vistos, clicar = [], []

    class MenuAnotado(QMenu):
        def exec(self, *_a):
            acoes = {acao.text(): acao for acao in self.actions() if acao.text()}
            vistos.append(set(acoes))
            if clicar:
                acoes[clicar.pop()].trigger()        # clica enquanto o menu existe

    monkeypatch.setattr("pestinha.controle.interacao.QMenu", MenuAnotado)
    clicar.append("Monitor neural")
    pet_app.show_pet_menu(None)
    assert "Monitor neural" in vistos[-1] and "Fechar o monitor neural" not in vistos[-1]
    clicar.append("Monitor neural")
    pet_app.show_pet_menu(None)                      # de novo: continua aberto (vem para a frente)
    assert "neural" in pet_app.floats.opened and "Fechar o monitor neural" in vistos[-1]
    clicar.append("Fechar o monitor neural")
    pet_app.show_pet_menu(None)
    assert "neural" not in pet_app.floats.opened


def test_clicar_de_novo_fecha_o_painel(pet_app):
    pet_app.floats.toggle("greve")
    pet_app.floats.toggle("greve")
    pet_app.floats.sync(pet_app.floats_allowed(), pet_app.floats_base())
    assert not pet_app.floats.window("greve").isVisible()


def test_esconder_o_bryan_esconde_o_painel(pet_app):
    pet_app.floats.open("greve")
    pet_app.floats.sync(False, False)
    assert not pet_app.floats.window("greve").isVisible()


# ---------------- modo teste e "Ao abrir" ----------------

def _app(tmp_path, **perms):
    app_qt = QApplication.instance() or QApplication([])
    app_qt.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS, configurado=True, **perms))
    app = PestinhaApp(store, paths)
    app.pet.show()
    app.update_visibility()
    return app


def _fechar(app):
    app.floats.hidden_by_tray = True
    for w in list(app.floats.windows.values()):
        w.close()


def test_modo_teste_abre_os_paineis_e_da_para_fechar_pelo_menu(tmp_path):
    app = _app(tmp_path, modo_teste=True, paineis_teste=True)
    try:
        assert app.floats.aberto("neural") and app.floats.aberto("greve")
        app.floats.close("neural")                                   # "Fechar o monitor neural"
        app.update_visibility()
        assert not app.floats.aberto("neural") and app.floats.aberto("greve")   # e continua fechado
        app.floats.open("neural")
        assert app.floats.aberto("neural")
    finally:
        _fechar(app)


def test_modo_teste_nao_abre_os_paineis_sozinho_por_padrao(tmp_path):
    app = _app(tmp_path, modo_teste=True)                            # como um permissions.json sem a chave nova
    try:
        assert not app.floats.aberto("neural") and not app.floats.aberto("greve")
        app.floats.open("greve")                                     # pelo menu, abre normalmente
        assert app.floats.aberto("greve")
    finally:
        _fechar(app)


def test_comeca_com_o_notebook_e_a_bolinha_na_tela_por_padrao(tmp_path):
    app = _app(tmp_path)
    try:
        assert not app.mesa.escondido and app.mesa.caderno.isVisible()
        assert not app.ball_stored and app.ball.isVisible()
    finally:
        _fechar(app)


def test_comeca_sem_o_notebook_e_sem_a_bolinha(tmp_path):
    app = _app(tmp_path, inicio_notebook=False, inicio_bolinha=False)
    try:
        assert app.mesa.escondido and not app.mesa.caderno.isVisible()
        assert app.ball_stored and not app.ball.isVisible()
        app.menu_alternar_notebook()                                 # pelo menu, aparecem
        app.menu_place_ball()
        assert app.mesa.caderno.isVisible() and app.ball.isVisible()
    finally:
        _fechar(app)


def test_sem_esconder_na_bandeja_e_o_sair_do_menu_fecha_o_programa(pet_app, monkeypatch):
    from PySide6.QtWidgets import QMenu
    textos_bandeja = [a.text() for a in pet_app.tray.menu.actions() if a.text()]
    assert "Esconder" not in textos_bandeja and "Mostrar" not in textos_bandeja and "Sair" in textos_bandeja
    vistos, saiu = [], []
    monkeypatch.setattr(pet_app, "quit", lambda: saiu.append(True))

    class MenuAnotado(QMenu):
        def exec(self, *_a):
            acoes = {acao.text(): acao for acao in self.actions() if acao.text()}
            vistos.append(set(acoes))
            acoes["Sair"].trigger()

    monkeypatch.setattr("pestinha.controle.interacao.QMenu", MenuAnotado)
    pet_app.show_pet_menu(None)
    assert not [t for t in vistos[-1] if t.startswith("Esconder (") or t == "Fechar"]
    assert saiu == [True]                                   # "Sair" fecha o programa, não some com o pet
