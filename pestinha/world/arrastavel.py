"""
ARRASTÁVEL - janela arrastável que flutua sobre a área de trabalho (painéis, notebook, placa).

Não tem gravidade nem é alvo do pouso do pet. Não tira o foco do programa
em que você está (WS_EX_NOACTIVATE) e fica sempre por cima. Arrasta-se
segurando o botão esquerdo em qualquer ponto; a posição é lembrada em
memory/panels.json (ver paths.py).
"""

from ..log import log
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from .. import plataforma
from ..body.pet import set_no_activate, set_normal
from ..mathutil import valor_real
from ..store import read_json, write_json


def load_positions(path):
    """Lê as posições salvas dos painéis (um dicionário), ou um vazio se não houver."""
    data = read_json(path, default={})
    return data if isinstance(data, dict) else {}


def save_position(path, key, x, y):
    """Guarda a posição de um painel pelo nome dele."""
    data = load_positions(path)
    data[key] = [x, y]
    try:
        write_json(path, data)
    except OSError as error:
        log(f"[painel] não salvou a posição: {error}")


def posicao_acessivel(salva, padrao, tamanho):
        """A posição salva se for válida e cair numa tela atual; senão o padrão; senão o canto da tela."""
        candidatos = []
        try:
            x, y = salva
            candidatos.append((valor_real(x, -1e5, 1e5), valor_real(y, -1e5, 1e5)))
        except (TypeError, ValueError):
            pass                                  # entrada inválida: ignora
        candidatos.append((padrao[0], padrao[1]))
        telas = [s.availableGeometry() for s in QGuiApplication.screens()]
        for x, y in candidatos:
            retangulo = QRect(int(x), int(y), tamanho[0], tamanho[1])
            if any(t.intersects(retangulo) for t in telas):
                return int(x), int(y)
        tela = QGuiApplication.primaryScreen().availableGeometry()
        return tela.x() + 20, tela.y() + 20


class FloatingWidget(QWidget):
    """
    Janela de painel que você pode arrastar, sem roubar o foco. `na_frente`: fica por cima de tudo, como o
    pet (o notebook, a plaquinha do castigo); senão, no nível normal (monitor neural, painel de protesto):
    quando você usa outro programa, ele fica por cima.
    """
    def __init__(self, app, key, title, size, minimum, default_pos, na_frente=True):
        """Cria o painel com título, tamanho (e tamanho mínimo) e a posição salva (ou a padrão)."""
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags | Qt.WindowStaysOnTopHint if na_frente else flags)
        self.na_frente = na_frente
        self.app = app
        self.key = key
        self.setWindowTitle(title)
        self.resize(*size)
        self.setMinimumSize(*minimum)
        self._grab = None
        saved = load_positions(app.paths.panels).get(key)
        self.move(*posicao_acessivel(saved, default_pos, size))

    def showEvent(self, event):
        """Ao aparecer, não rouba o foco do programa que você está usando."""
        super().showEvent(event)
        (set_no_activate if self.na_frente else set_normal)(self)

    def trazer_para_frente(self):
        """Mostra e põe na frente das outras janelas (um painel normal pode estar atrás de outro programa)."""
        self.show()
        self.raise_()
        try:
            plataforma.trazer_para_frente(int(self.winId()))
        except Exception:
            pass

    def mousePressEvent(self, event):
        """Começa a arrastar o painel pelo clique."""
        if event.button() == Qt.LeftButton:
            self._grab = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._botao = event.button()

    def mouseMoveEvent(self, event):
        """Move o painel enquanto você arrasta."""
        if self._grab is not None:
            self.move(event.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, event):
        """Solta o painel e para de arrastar."""
        if self._grab is not None and event.button() == getattr(self, "_botao", Qt.LeftButton):
            self._grab = None
            save_position(self.app.paths.panels, self.key, self.x(), self.y())
