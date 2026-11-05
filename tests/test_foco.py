"""Regressão de foco: overlays não ativam o app ao aparecer ou mudar de ordem.

Verificação nativa no macOS:
QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM=1 QT_QPA_PLATFORM=cocoa python -m pytest tests/test_foco.py -q
O primeiro ajuste evita apenas a ativação inicial do processo de teste pelo Qt.
"""

import os
from types import SimpleNamespace

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pestinha import plataforma
from pestinha.body.bolinha import Ball
from pestinha.body.pet import PetWindow, raise_without_activating, set_always_on_top
from pestinha.body.pet_state import PetState
from pestinha.mind.mesa import MesaController
from pestinha.world.arrastavel import FloatingWidget
from pestinha.world.fireworks import Fireworks
from pestinha.world.objetos import NoteThing


@pytest.fixture
def qt():
    app = QApplication.instance() or QApplication([])
    set_always_on_top(True)
    yield app
    set_always_on_top(True)


def test_erro_nativo_nao_recai_em_raise_que_rouba_foco(qt, monkeypatch):
    pet = PetWindow(100, 100, PetState())
    pet.show()

    def falhar(_janela_id):
        raise RuntimeError("janela indisponível")

    def ativacao_proibida():
        pytest.fail("raise_ pode ativar o aplicativo no macOS")

    monkeypatch.setattr(plataforma, "elevar_sem_foco", falhar)
    monkeypatch.setattr(pet, "raise_", ativacao_proibida)
    raise_without_activating(pet)


@pytest.mark.parametrize("tipo", ["pet", "bolinha", "bilhete", "painel", "fogos", "notebook"])
def test_cocoa_mantem_aplicativo_ativo_ao_mostrar_e_reordenar(qt, tmp_path, tipo):
    if qt.platformName() != "cocoa":
        pytest.skip("Requer Qt Cocoa e uma sessão gráfica macOS")
    import objc
    from AppKit import (
        NSWorkspace,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorMoveToActiveSpace,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
    )

    QTest.qWait(100)
    workspace = NSWorkspace.sharedWorkspace()
    pid_ativo = workspace.frontmostApplication().processIdentifier()
    assert pid_ativo != os.getpid(), "Deixe outro aplicativo ativo durante o teste"

    mesa = None
    if tipo == "notebook":
        app = SimpleNamespace(
            paths=SimpleNamespace(panels=tmp_path / "panels.json"),
            conteudo=SimpleNamespace(notebook=tmp_path / "notebook.png"), nome="Teste",
        )
        mesa = MesaController(lambda: False, app)
        janela = mesa.caderno
        mesa.decisao.at_desk = True
        mesa.ancora = (janela.x(), janela.y())
        pet = PetWindow(100, 100, PetState())
    elif tipo == "pet":
        janela = PetWindow(100, 100, PetState())
    elif tipo == "bolinha":
        janela = Ball(100, 100)
    elif tipo == "bilhete":
        janela = NoteThing("Teste de foco")
    elif tipo == "fogos":
        janela = Fireworks()
    else:
        app = SimpleNamespace(paths=SimpleNamespace(panels=tmp_path / "panels.json"))
        janela = FloatingWidget(app, "teste", "Teste de foco", (100, 100), (50, 50), (100, 100))

    try:
        for passo, por_cima in enumerate((True, False, True)):
            set_always_on_top(por_cima)
            janela.show()
            QTest.qWait(50)
            assert workspace.frontmostApplication().processIdentifier() == pid_ativo
            if mesa is not None:
                mesa.pin(pet.body, float(passo))
            else:
                raise_without_activating(janela)
            QTest.qWait(50)
            assert workspace.frontmostApplication().processIdentifier() == pid_ativo
            nativa = objc.objc_object(c_void_p=int(janela.winId())).window()
            assert nativa.isVisible()
            assert not nativa.canBecomeKeyWindow()
            assert not nativa.hidesOnDeactivate()
            behavior = nativa.collectionBehavior()
            assert behavior & NSWindowCollectionBehaviorCanJoinAllSpaces
            assert not behavior & NSWindowCollectionBehaviorMoveToActiveSpace
            assert behavior & NSWindowCollectionBehaviorFullScreenAuxiliary
            from AppKit import NSModalPanelWindowLevel, NSNormalWindowLevel
            assert nativa.level() == (NSModalPanelWindowLevel if por_cima else NSNormalWindowLevel)
            assert bool(janela.windowFlags() & Qt.WindowStaysOnTopHint) == por_cima
            janela.hide()
    finally:
        janela.close()


def test_cocoa_sempre_por_cima_sobrevive_a_troca_de_app(qt):
    if qt.platformName() != "cocoa":
        pytest.skip("Requer Qt Cocoa e uma sessão gráfica macOS")
    import objc
    from AppKit import (
        NSApplication, NSModalPanelWindowLevel, NSWorkspace,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
    )

    workspace = NSWorkspace.sharedWorkspace()
    anterior = workspace.frontmostApplication()
    assert anterior.processIdentifier() != os.getpid()
    pet = PetWindow(100, 100, PetState())
    pet.show()
    nativa = objc.objc_object(c_void_p=int(pet.winId())).window()
    try:
        for _ in range(2):
            # Simula abrir as configurações e depois voltar ao editor.
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            QTest.qWait(150)
            assert workspace.frontmostApplication().processIdentifier() == os.getpid()
            anterior.activateWithOptions_(0)
            QTest.qWait(150)
            assert workspace.frontmostApplication().processIdentifier() == anterior.processIdentifier()
            assert nativa.isVisible()
            assert nativa.level() == NSModalPanelWindowLevel
            assert nativa.collectionBehavior() & NSWindowCollectionBehaviorCanJoinAllSpaces
            assert not nativa.canBecomeKeyWindow()
    finally:
        pet.close()
        anterior.activateWithOptions_(0)
