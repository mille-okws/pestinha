"""Eddie: conteúdo próprio, piadas por contexto, permissões e intervalo entre comentários."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pestinha import config
from pestinha.ajustes import INTERVALO_COMENTARIO_NOTEBOOK_S, INTERVALO_COMENTARIO_S
from pestinha.core.episodic import EpisodicMemory
from pestinha.core.protesto import DEFAULT_SIGNS, load_signs
from pestinha.core.nervous_system import LIFBrain
from pestinha.mind.mesa import DeskController
from pestinha.mind.mischief_ctl import MischiefController
from pestinha.paths import Paths
from pestinha.settings_store import SettingsStore
from pestinha.world.mischief import MischiefEngine

ROOT = Path(__file__).resolve().parents[1]
PATHS = Paths(root=ROOT)


@pytest.fixture
def controller(tmp_path):
    qt = QApplication.instance() or QApplication([])
    assert qt is not None
    engine = MischiefEngine(PATHS.conteudo("eddie"))
    memory = EpisodicMemory(tmp_path / "episodes.jsonl", tmp_path / "prefs.json")
    ctl = MischiefController(engine, memory, Mock(), Mock(), Mock(), Mock(), lambda: False)
    yield ctl
    engine.clear()


def comentar(ctl, now=100.0, **overrides):
    args = dict(activity="PROGRAMMING", emotion="contente", seated=False,
                perms=dict(config.DEFAULT_PERMISSIONS, travessuras=True, memes=False, bilhetes=True),
                prof=config.PROFILES["normal"], fullscreen=False, blocked=False)
    args.update(overrides)
    return ctl.maybe_comment(now, (0, 0, 1600, 1000), (800, 500), **args)


def test_eddie_tem_personalidade_e_conteudo_completos():
    assert "eddie" in config.list_pets(PATHS)
    pet = config.load_pet(PATHS, "eddie")
    assert pet["nome"] == "Eddie"
    assert pet["aparencia"]["acessorios"]["oculos"]
    conteudo = PATHS.conteudo("eddie")
    signs = load_signs(conteudo.signs)
    assert all(signs[s] and not set(signs[s]) & set(DEFAULT_SIGNS[s]) for s in DEFAULT_SIGNS)
    for ctx in ("ide", "notebook"):
        assert len(config.Notes(conteudo.comentarios(ctx)).pick()) > 0
        assert len(config.list_images(conteudo.memes_contexto(ctx))) >= 4
    images = list(conteudo.memes.rglob("*.png"))
    assert len(images) == 22
    assert all(not QImage(str(path)).isNull() for path in images)


def test_temperamento_favorece_notebook_com_trabalho_e_distracoes():
    pet = config.load_pet(PATHS, "eddie")
    tempos = []
    for temperamento in ({}, pet["temperamento"]):
        brain = LIFBrain(seed=pet["seed"], temperament=temperamento)
        brain.rng = np.random.default_rng(42)
        mesa = DeskController()
        sentado = 0
        for i in range(100):
            brain.stimulate({"WORK": 0.35, "TYPING": 0.2, "NOVELTY": 0.2,
                             "BOREDOM": 0.3, "TOY_NEAR": 0.3})
            brain.step(100)
            mesa.tick(i / 10, brain.motor_activity()["SENTAR"], True)
            sentado += mesa.at_desk
        tempos.append(sentado)
    assert tempos[1] > tempos[0] + 30


def test_ide_comenta_na_entrada_e_nao_a_cada_frame(controller):
    assert comentar(controller) == "bilhete"
    notes = config.Notes(PATHS.conteudo("eddie").comentarios("ide"))
    assert notes.has_lines()
    assert controller.engine.things[0].text in notes.lines
    for now in (100.016, 101.0, 110.0, 190.0):
        assert comentar(controller, now) is None
    assert len(controller.engine.things) == 1
    assert len(controller.memory.open) == 1
    assert controller.memory.open[0]["contexto"] == "PROGRAMMING|contente"
    comentar(controller, 191.0, activity="BROWSING")
    assert comentar(controller, 192.0) == "bilhete"


def test_alternar_rapido_entre_ide_e_browser_nao_vira_spam(controller):
    assert comentar(controller) == "bilhete"
    for now in range(101, int(100 + INTERVALO_COMENTARIO_S)):
        comentar(controller, float(now), activity="BROWSING")
        assert comentar(controller, now + 0.1) is None
    assert len(controller.engine.things) == 1


def test_mudar_entre_ferramentas_de_programacao_tambem_e_entrada(controller):
    assert comentar(controller, program="codex") == "bilhete"
    assert comentar(controller, 101.0, program="pycharm") is None
    assert comentar(controller, 102.0, program="codex") is None
    assert comentar(controller, 100.0 + INTERVALO_COMENTARIO_S, program="pycharm") == "bilhete"
    assert len(controller.engine.things) == 2


def test_notebook_comenta_sentado_sem_exigir_que_ele_saia_da_mesa(controller):
    assert comentar(controller, activity="IDLE", seated=True) == "bilhete"
    assert comentar(controller, 101.0, activity="IDLE", seated=True) is None
    assert comentar(controller, 100 + INTERVALO_COMENTARIO_NOTEBOOK_S,
                    activity="IDLE", seated=True) == "bilhete"
    assert comentar(controller, 1000.0, activity="IDLE", seated=False) is None


@pytest.mark.parametrize("overrides", [
    {"blocked": True}, {"fullscreen": True}, {"emotion": "dormindo"}, {"emotion": "triste"},
    {"perms": dict(config.DEFAULT_PERMISSIONS, travessuras=False)},
    {"perms": dict(config.DEFAULT_PERMISSIONS, travessuras=True, ativo=False)},
    {"perms": dict(config.DEFAULT_PERMISSIONS, travessuras=True, memes=False, bilhetes=False)},
])
def test_restricoes_descartam_evento_sem_fila_para_depois(controller, overrides):
    assert comentar(controller, **overrides) is None
    assert comentar(controller, 101.0) is None
    assert not controller.engine.things
    assert not controller.memory.open


def test_limite_de_objetos_e_penalidade_continuam_valendo(controller):
    assert comentar(controller, prof=dict(config.PROFILES["normal"], max_objects=0)) is None
    comentar(controller, 101.0, activity="IDLE")
    controller.penalty_until = 200.0
    assert comentar(controller, 102.0) is None
    assert not controller.engine.things


def test_pode_usar_so_memes_ou_so_bilhetes_e_fechar_com_clique(controller):
    perms = dict(config.DEFAULT_PERMISSIONS, travessuras=True, memes=True, bilhetes=False)
    assert comentar(controller, perms=perms) == "meme"
    thing = controller.engine.things[0]
    controller.engine._on_click(thing)
    assert not controller.engine.things


@pytest.mark.parametrize("pet", ["bryan", "jorge"])
def test_pets_sem_frases_contextuais_mantem_comportamento(controller, pet):
    controller.engine = MischiefEngine(PATHS.conteudo(pet))
    assert comentar(controller) is None
    assert comentar(controller, 200.0, seated=True) is None
    assert not controller.engine.things


def test_eddie_no_app_reage_a_ide_sem_mudar_o_personagem_salvo(tmp_path, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    assert qt is not None
    import pestinha.app as app_mod
    paths = Paths(root=ROOT, dados=tmp_path)
    store = SettingsStore(paths)
    store.update({"pet": "eddie", "travessuras": True, "memes": False})
    monkeypatch.setattr(app_mod, "PanicHotkey", lambda: SimpleNamespace(ok=True, pressed=Mock()))
    monkeypatch.setattr(app_mod.senses, "get_active_app", lambda: "pycharm")
    monkeypatch.setattr(app_mod.senses, "get_idle_seconds", lambda: 0.0)
    monkeypatch.setattr(app_mod.senses, "is_fullscreen", lambda: False)
    app = app_mod.PestinhaApp(store, paths)
    for timer in app.findChildren(QTimer):
        timer.stop()
    app.maybe_mischief(100.0, 0.016, (0, 0, 1600, 1000), (800, 500), {})
    assert app.nome == "Eddie"
    assert app.activity == "PROGRAMMING"
    assert app.pet_paths.base == tmp_path / "pets" / "eddie"
    assert len(app.mischief.things) == 1
    assert store["pet"] == "eddie"
    app.open_settings()
    assert "6 de trabalho, 4 de notebook" in app.settings.resumo.text()
