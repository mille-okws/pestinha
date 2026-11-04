"""
ARRASTÁVEL - janela arrastável que flutua sobre a área de trabalho (painéis, notebook, placa).

Não tem gravidade nem é alvo do pouso do pet. Não tira o foco do programa
em que você está (WS_EX_NOACTIVATE) e fica sempre por cima. Arrasta-se
segurando o botão esquerdo em qualquer ponto; a posição é lembrada em
memory/panels.json (ver paths.py).

No Hyprland (Wayland), o `move()` do Qt é ignorado e a janela nova nasce
tiled (ocupando o workspace inteiro): por isso, aqui, quem flutua, fixa e
move a janela é o backend da plataforma (`configurar_janela`/`mover_janela`),
igual às janelas do pet.
"""

from ..log import log
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from ..body.pet import reposicionar, set_no_activate
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
    """Janela de painel que você pode arrastar, sempre por cima, sem roubar o foco."""
    def __init__(self, app, key, title, size, minimum, default_pos):
        """Cria o painel com título, tamanho (e tamanho mínimo) e a posição salva (ou a padrão)."""
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool
                         | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.app = app
        self.key = key
        self.setWindowTitle(title)
        self.resize(*size)
        self.setMinimumSize(*minimum)
        self._tamanho = (self.width(), self.height())
        self._grab = None
        saved = load_positions(app.paths.panels).get(key)
        self._pos_desejada = posicao_acessivel(saved, default_pos, size)
        reposicionar(self, *self._pos_desejada, tamanho=self._tamanho)

    def showEvent(self, event):
        """Ao aparecer, não rouba o foco do programa que você está usando."""
        super().showEvent(event)
        set_no_activate(self)
        # o compositor pode ter dilatado a janela para o tamanho do workspace:
        # pede de volta o tamanho original antes de reposicionar
        self.resize(*self._tamanho)
        # No Hyprland o cliente pode ainda não existir no compositor neste instante:
        # tenta de novo em 100/300/800 ms até o backend achar o endereço e configurar.
        for atraso in (100, 300, 800):
            QTimer.singleShot(atraso, lambda: reposicionar(self, *self._pos_desejada, tamanho=self._tamanho))

    def mousePressEvent(self, event):
        """Começa a arrastar o painel pelo clique."""
        if event.button() == Qt.LeftButton:
            self._grab = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._botao = event.button()

    def mouseMoveEvent(self, event):
        """Move o painel enquanto você arrasta."""
        if self._grab is not None:
            pos = event.globalPosition().toPoint() - self._grab
            self._pos_desejada = (pos.x(), pos.y())
            reposicionar(self, pos.x(), pos.y(), tamanho=self._tamanho)

    def mouseReleaseEvent(self, event):
        """Solta o painel e para de arrastar."""
        if self._grab is not None and event.button() == getattr(self, "_botao", Qt.LeftButton):
            self._grab = None
            save_position(self.app.paths.panels, self.key, self.x(), self.y())
