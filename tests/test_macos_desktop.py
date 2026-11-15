"""Regressão Cocoa: QT_QPA_PLATFORM=cocoa python -m pytest tests/test_macos_desktop.py."""
import sys
import pytest
from PySide6.QtWidgets import QApplication
from pestinha.body.pet import PetWindow
from pestinha.body.pet_state import PetState


@pytest.mark.skipif(sys.platform != "darwin", reason="Requer macOS")
def test_pet_nao_e_ocultado_pelo_macos_ao_desativar_app():
    app = QApplication.instance() or QApplication([])
    if app.platformName() != "cocoa":
        pytest.skip("Requer QT_QPA_PLATFORM=cocoa")
    from AppKit import NSApplication
    pet = PetWindow(100, 100, PetState())
    pet.setWindowTitle("Pestinha regressao Cocoa")
    try:
        pet.show()
        app.processEvents()
        windows = [w for w in NSApplication.sharedApplication().windows()
                   if w.title() == "Pestinha regressao Cocoa"]
        assert len(windows) == 1
        assert not windows[0].hidesOnDeactivate()
    finally:
        pet.close()
