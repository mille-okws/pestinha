"""
JANELA NA FRENTE - no macOS o pet não some ao trocar de programa; as Configurações pedem o foco.

No macOS o Qt.Tool vira um NSPanel que some quando o programa perde o foco. Depois de corrigido,
clicar no pet não ativa mais o programa, e por isso as Configurações precisam pedir o foco ao abrir.
Sem tela de verdade, aqui se testa o que é pedido ao sistema, não o que aparece.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pestinha.controle.sessao import SessaoMixin  # noqa: E402


@pytest.fixture
def macos():
    return pytest.importorskip("pestinha.plataforma.macos", exc_type=ImportError)


class PainelFalso:
    """Imita o NSPanel que o Qt cria para uma janela Qt.Tool (valores lidos de um macOS real)."""

    def __init__(self):
        self.some_ao_desativar = True
        self.mascara = 0xe
        self.comportamento = 0x102

    def setHidesOnDeactivate_(self, valor):
        self.some_ao_desativar = valor

    def styleMask(self):
        return self.mascara

    def setStyleMask_(self, valor):
        self.mascara = valor

    def setCollectionBehavior_(self, valor):
        self.comportamento = valor


def test_painel_nao_some_quando_o_programa_perde_o_foco(macos):
    painel = PainelFalso()
    macos.manter_na_frente(painel)
    assert painel.some_ao_desativar is False


def test_painel_nao_ativa_o_programa_e_preserva_o_resto_da_mascara(macos):
    painel = PainelFalso()
    macos.manter_na_frente(painel)
    assert painel.mascara == 0xe | macos.PAINEL_SEM_ATIVAR


def test_painel_aparece_em_todos_os_spaces_e_sobre_tela_cheia(macos):
    painel = PainelFalso()
    macos.manter_na_frente(painel)
    assert painel.comportamento == (1 << 0) | (1 << 4) | (1 << 8)


class AppFalso:
    """Imita o QApplication criado, só no que sem_foco_nativo pergunta."""

    def __init__(self, plataforma):
        self.plataforma = plataforma

    def platformName(self):
        return self.plataforma


def _qt(monkeypatch, macos, app):
    """Troca o QApplication do módulo. Como no Qt de verdade, sem instância o platformName() responde "cocoa"."""
    plataforma = (lambda: app.platformName()) if app else (lambda: "cocoa")
    monkeypatch.setattr(macos, "QApplication", SimpleNamespace(instance=lambda: app, platformName=plataforma))


@pytest.fixture
def nativo(macos, monkeypatch):
    """Imita o pyobjc e o ajuste: um id usado como ponteiro aparece em `ids`, sem derrubar o pytest."""
    chamadas = SimpleNamespace(ids=[], ajustadas=[], janela=object())

    def objc_object(c_void_p):
        chamadas.ids.append(c_void_p)
        return SimpleNamespace(window=lambda: chamadas.janela)

    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(objc_object=objc_object))
    monkeypatch.setattr(macos, "manter_na_frente", chamadas.ajustadas.append)
    return chamadas


def test_sem_qapplication_o_id_nao_vira_ponteiro(macos, monkeypatch, nativo):
    """Sem app o Qt diz "cocoa" mesmo assim; usar o id como NSView derrubava o processo (SIGSEGV)."""
    _qt(monkeypatch, macos, None)
    macos.sem_foco_nativo(12345)
    assert nativo.ids == [] and nativo.ajustadas == []


def test_no_qt_offscreen_o_id_nao_vira_ponteiro(macos, monkeypatch, nativo):
    """No Qt offscreen o id é um contador: usá-lo como NSView derrubaria o processo inteiro."""
    _qt(monkeypatch, macos, AppFalso("offscreen"))
    macos.sem_foco_nativo(12345)
    assert nativo.ids == [] and nativo.ajustadas == []


def test_no_cocoa_ajusta_a_janela_dona_do_id(macos, monkeypatch, nativo):
    _qt(monkeypatch, macos, AppFalso("cocoa"))
    macos.sem_foco_nativo(12345)
    assert nativo.ids == [12345]
    assert nativo.ajustadas == [nativo.janela]


def test_no_cocoa_sem_pyobjc_o_pet_continua_funcionando(macos, monkeypatch, nativo):
    _qt(monkeypatch, macos, AppFalso("cocoa"))
    monkeypatch.setitem(sys.modules, "objc", None)      # `import objc` passa a falhar
    macos.sem_foco_nativo(12345)
    assert nativo.ajustadas == []


def test_configuracoes_pedem_o_foco_ao_abrir(monkeypatch):
    dialogo = Mock()
    monkeypatch.setattr("pestinha.controle.sessao.SettingsDialog", lambda *_a, **_k: dialogo)
    app = SimpleNamespace(settings=None, perms={}, paths=None, timeline=Mock(),
                          apply_perms=Mock(), wipe_all_data=Mock())
    SessaoMixin.open_settings(app)
    dialogo.show.assert_called_once()
    dialogo.activateWindow.assert_called_once()


def test_configuracoes_ja_abertas_pedem_o_foco_sem_abrir_outra(monkeypatch):
    dialogo = Mock()
    dialogo.isVisible.return_value = True
    outra = Mock()
    monkeypatch.setattr("pestinha.controle.sessao.SettingsDialog", outra)
    SessaoMixin.open_settings(SimpleNamespace(settings=dialogo))
    outra.assert_not_called()
    dialogo.raise_.assert_called_once()
    dialogo.activateWindow.assert_called_once()
