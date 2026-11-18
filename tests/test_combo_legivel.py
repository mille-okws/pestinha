"""
A lista do combo de personagem fica legível com o sistema no tema claro.

O fundo da lista vinha do tema do sistema (branco) e o texto vinha do combo (verde-claro), então os
itens sumiam. O teste força um tema claro e confere o fundo e o contraste do texto na lista aberta.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QVBoxLayout  # noqa: E402

from pestinha.ui.ui import STYLE  # noqa: E402


def _luminancia(cor):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(cor.red()) + 0.7152 * canal(cor.green()) + 0.0722 * canal(cor.blue())


def _contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_lista_do_combo_legivel_com_sistema_no_tema_claro():
    app = QApplication.instance() or QApplication([])
    paleta_original = app.palette()
    claro = QPalette()
    for papel, cor in [(QPalette.Window, "#efefef"), (QPalette.Base, "#ffffff"),
                       (QPalette.Text, "#000000"), (QPalette.WindowText, "#000000")]:
        claro.setColor(papel, QColor(cor))
    app.setPalette(claro)
    try:
        dialogo = QDialog()
        dialogo.setStyleSheet(STYLE)
        combo = QComboBox()
        combo.addItems(["Bryan", "Jorge"])
        QVBoxLayout(dialogo).addWidget(combo)
        dialogo.show()
        combo.showPopup()
        app.processEvents()

        lista = combo.view()
        imagem = lista.viewport().grab().toImage()
        linha = lista.visualRect(lista.model().index(1, 0))   # "Jorge": item não selecionado
        fundo = imagem.pixelColor(imagem.width() - 3, linha.center().y())
        assert _luminancia(fundo) < 0.1, f"fundo da lista claro demais: {fundo.name()}"

        texto = max((imagem.pixelColor(x, y) for x in range(linha.left(), linha.right())
                     for y in range(linha.top(), linha.bottom())),
                    key=lambda c: _contraste(c, fundo))
        assert _contraste(texto, fundo) >= 4.5, f"texto {texto.name()} sobre {fundo.name()}"
        combo.hidePopup()
    finally:
        app.setPalette(paleta_original)
