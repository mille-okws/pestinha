"""
Preparar antes de mostrar: a fila (um modelo por vez), a voz gerada antes do post-it ou cartaz e apagada
depois, a rede escolhendo frase nova ou já escrita (INVENTAR) e quando espiar a tela (ESPIAR).
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pestinha import config
from pestinha.core.nervous_system import DECISION_MOTORS, MODULADORES, MOTOR_SPEC, LIFBrain
from pestinha.mind import espiar_ctl
from pestinha.mind.fala_ctl import FalaController, reduzir_print
from pestinha.mind.mischief_ctl import chance_de_inventar
from pestinha.mind.preparo import Cancelada, Controle, Preparo, Tarefa
from pestinha.mind.voz import para_fala
from pestinha.paths import Paths

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ia_local import _instalada_falsa, _usar_llama_falso, llama_falso, resposta_qwen  # noqa: E402
from test_voz import MotorFalso, SistemaFalso  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _esperar(qapp, cond, tempo=10.0):
    fim = time.monotonic() + tempo
    while time.monotonic() < fim and not cond():
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


# ---------------- a fila ----------------

def test_uma_tarefa_por_vez_na_ordem_e_entregue_na_tela(qapp):
    preparo = Preparo()
    eventos, entregues, threads = [], [], []
    trava = threading.Lock()

    def trabalho(nome):
        def rodar(_controle):
            with trava:
                eventos.append(("começou", nome))
            time.sleep(0.05)
            with trava:
                eventos.append(("terminou", nome))
            return nome
        return rodar

    def chegou(resultado):
        entregues.append(resultado)
        threads.append(threading.current_thread() is threading.main_thread())

    for nome in ("a", "b", "c"):
        assert preparo.pedir(Tarefa(nome, trabalho(nome), chegou))
    assert _esperar(qapp, lambda: len(entregues) == 3)
    assert entregues == ["a", "b", "c"] and all(threads)
    assert eventos == [(e, n) for n in "abc" for e in ("começou", "terminou")]     # nunca duas juntas
    assert _esperar(qapp, lambda: not preparo.ocupado())


def test_fila_cheia_recusa(qapp):
    preparo = Preparo(max_fila=2)
    solta = threading.Event()
    assert preparo.pedir(Tarefa("a", lambda c: solta.wait(5), lambda r: None))
    assert preparo.pedir(Tarefa("b", lambda c: None, lambda r: None))
    assert not preparo.pedir(Tarefa("c", lambda c: None, lambda r: None))
    assert preparo.rotulos()[0] == "a"
    solta.set()
    assert _esperar(qapp, lambda: not preparo.ocupado())


def test_tarefa_que_falha_avisa_e_a_fila_continua(qapp):
    preparo = Preparo()
    falhas, prontas = [], []

    def quebra(_c):
        raise RuntimeError("o llama.cpp saiu com o código 2")
    preparo.pedir(Tarefa("ruim", quebra, prontas.append, ao_falhar=falhas.append))
    preparo.pedir(Tarefa("boa", lambda c: "ok", prontas.append))
    assert _esperar(qapp, lambda: prontas)
    assert falhas == ["o llama.cpp saiu com o código 2"] and prontas == ["ok"]


def test_controle_tem_limite_de_tempo():
    with pytest.raises(RuntimeError, match="passou de"):
        Controle().rodar([sys.executable, "-c", "import time; time.sleep(10)"], tempo=0.3)
    r = Controle().rodar([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], entrada=b"oi")
    assert r.returncode == 0 and r.stdout.strip() == b"OI"


def test_cancelar_mata_o_programa_e_avisa_quem_pediu(qapp):
    preparo = Preparo()
    canceladas, prontas, descartadas = [], [], []
    lento = [sys.executable, "-c", "import time; time.sleep(30)"]
    preparo.pedir(Tarefa("rodando", lambda c: c.rodar(lento, tempo=60), prontas.append,
                         ao_cancelar=lambda: canceladas.append("rodando")))
    preparo.pedir(Tarefa("na fila", lambda c: "x", prontas.append, ao_cancelar=lambda: canceladas.append("na fila")))
    assert _esperar(qapp, lambda: preparo.rotulos()[:1] == ["rodando"])
    time.sleep(0.2)                                          # o programa lento já abriu
    inicio = time.monotonic()
    preparo.cancelar()
    assert _esperar(qapp, lambda: not preparo.ocupado(), tempo=5)
    assert time.monotonic() - inicio < 5                     # matou, não esperou os 30 s
    assert sorted(canceladas) == ["na fila", "rodando"] and prontas == [] and descartadas == []


def test_o_que_ficou_pronto_depois_de_cancelar_e_descartado(qapp):
    preparo = Preparo()
    solta, descartados, prontas = threading.Event(), [], []
    preparo.pedir(Tarefa("áudio", lambda c: (solta.wait(5), "fala.wav")[1], prontas.append,
                         descartar=descartados.append))
    time.sleep(0.05)
    preparo.cancelar()                                       # não usa o controle: termina mesmo assim
    solta.set()
    assert _esperar(qapp, lambda: descartados)
    assert descartados == ["fala.wav"] and prontas == []


def test_controle_cancelado_nao_abre_mais_nada():
    c = Controle()
    c.cancelar()
    with pytest.raises(Cancelada):
        c.rodar([sys.executable, "-c", "print(1)"])


# ---------------- preparar a fala (com dublês) ----------------

class VozFalsa:
    """Anota a ordem: preparar (na fila), anexar e descartar (na tela)."""

    def __init__(self, natural=True, pasta=None):
        self._natural, self.pasta, self.ordem = natural, pasta, []

    def natural(self):
        return self._natural

    def preparar(self, texto, emocao=None, rodar=None):
        self.ordem.append(("voz", texto, emocao))
        arquivo = self.pasta / "fala.wav"
        arquivo.write_bytes(b"RIFF")
        return arquivo

    def anexar(self, texto, arquivo):
        self.ordem.append(("anexar", texto))

    def descartar(self, texto):
        self.ordem.append(("descartar", texto))


def _fala(tmp_path, natural=True, perms=None):
    voz = VozFalsa(natural, tmp_path)
    sistema = type("S", (), {"TEM_VOZ": True})
    perms = perms or {"voz": True}
    return FalaController(Preparo(), voz, tmp_path / "ia_local", lambda: perms, lambda: False, sistema), voz


def test_escreve_depois_gera_a_voz_depois_mostra(qapp, tmp_path):
    fala, voz = _fala(tmp_path)

    def escrever(_c):
        voz.ordem.append(("escreveu",))
        return "frase nova", None
    mostradas = []
    assert fala.preparar("post-it", lambda f: (voz.ordem.append(("mostrar", f)), mostradas.append(f)),
                         escrever=escrever, emocao="feliz")
    assert _esperar(qapp, lambda: mostradas)
    assert voz.ordem == [("escreveu",), ("voz", "frase nova", "feliz"), ("anexar", "frase nova"),
                         ("mostrar", "frase nova"), ("descartar", "frase nova")]


def test_sem_voz_natural_texto_pronto_nao_precisa_esperar(tmp_path):
    fala, _ = _fala(tmp_path, natural=False)
    assert not fala.precisa_preparar() and fala.precisa_preparar(escrever=lambda c: ("x", None))
    desligada, _ = _fala(tmp_path, perms={"voz": False})
    assert not desligada.voz_natural()


def test_se_nao_escreveu_nada_nao_gera_voz(qapp, tmp_path):
    fala, voz = _fala(tmp_path)
    falhas = []
    fala.preparar("post-it", lambda f: None, escrever=lambda c: (None, "nenhuma das 3 respostas serviu"),
                  ao_falhar=falhas.append)
    assert _esperar(qapp, lambda: falhas)
    assert falhas == ["nenhuma das 3 respostas serviu"] and voz.ordem == []


def test_cancelado_com_o_audio_pronto_apaga_o_audio(qapp, tmp_path):
    fala, voz = _fala(tmp_path)
    solta, mostradas = threading.Event(), []
    fala.preparar("post-it", mostradas.append, escrever=lambda c: (solta.wait(5), ("frase", None))[1])
    time.sleep(0.05)
    fala.preparo.cancelar()
    solta.set()
    assert _esperar(qapp, lambda: not fala.preparo.ocupado())
    assert mostradas == [] and not (tmp_path / "fala.wav").exists()


def _png(caminho, largura=2560, altura=1600):
    from PySide6.QtGui import QColor, QImage
    imagem = QImage(largura, altura, QImage.Format_RGB32)
    imagem.fill(QColor("white"))
    assert imagem.save(str(caminho), "PNG")


def test_print_e_reduzido_antes_de_o_modelo_olhar(qapp, tmp_path):
    from PySide6.QtGui import QImage
    _png(tmp_path / "tela.png")
    assert reduzir_print(tmp_path / "tela.png")
    assert QImage(str(tmp_path / "tela.png")).width() == 1280
    (tmp_path / "vazio.png").write_bytes(b"")
    assert not reduzir_print(tmp_path / "vazio.png")


def test_comentar_tira_o_print_na_fila_e_apaga(qapp, tmp_path, monkeypatch):
    fala, _ = _fala(tmp_path, natural=False)
    prints = []

    def capturar(destino):
        prints.append(Path(destino))
        _png(destino)
        return True
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("você está programando de novo?")])
    _usar_llama_falso(monkeypatch, prog)
    mostradas = []
    fala.preparar("espiada", mostradas.append,
                  escrever=fala.comentador("Bryan", None, {"emocao": "curioso"}, capturar=capturar))
    assert _esperar(qapp, lambda: mostradas)
    assert mostradas == ["você está programando de novo?"]
    assert f"--image {prints[0]}" in chamadas.read_text(encoding="utf-8")   # o modelo olhou o print
    assert not prints[0].exists()                            # e ele sumiu logo depois


def test_sem_permissao_de_tela_nao_comenta(qapp, tmp_path):
    fala, _ = _fala(tmp_path, natural=False)
    falhas = []
    fala.preparar("espiada", lambda f: None, ao_falhar=falhas.append,
                  escrever=fala.comentador("Bryan", None, {}, capturar=lambda destino: False))
    assert _esperar(qapp, lambda: falhas)
    assert "Gravação de Tela" in falhas[0]


# ---------------- a rede decide ----------------

def test_motores_novos_na_rede():
    nomes = [m[0] for m in MOTOR_SPEC]
    assert "INVENTAR" in nomes and "ESPIAR" in nomes and LIFBrain().N == 490
    assert "ESPIAR" in DECISION_MOTORS and "INVENTAR" in MODULADORES and "INVENTAR" not in DECISION_MOTORS


def test_inventar_nao_compete_com_ninguem_e_espiar_compete_com_as_decisoes():
    b = LIFBrain(seed=1)

    def bloco(pre, post):
        a, c = b.pool(pre), b.pool(post)
        return b.W[a["start"]:a["start"] + a["n"], c["start"]:c["start"] + c["n"]]
    outros = [m[0] for m in MOTOR_SPEC if m[0] != "INVENTAR"]
    assert all(not np.any(bloco("INVENTAR", m) < 0) and not np.any(bloco(m, "INVENTAR") < 0) for m in outros)
    assert np.any(bloco("ESPIAR", "TRAVESSURA") < 0) and np.any(bloco("TRAVESSURA", "ESPIAR") < 0)
    assert not np.any(bloco("ESPIAR", "STARTLE") < 0)               # decisão não inibe expressão


def _taxa(estado, motor, segundos=10):
    taxas = []
    for seed in (1, 2):
        b = LIFBrain(seed=seed)
        for passo in range(int(segundos * 20)):
            b.stimulate(estado)
            b.step(50)
            if passo >= segundos * 10:
                taxas.append(b.motor_activity()[motor])
    return float(np.mean(taxas))


def test_entediado_inventa_e_cansado_nao():
    entediado = _taxa({"SILENCE": 0.6, "BOREDOM": 0.9}, "INVENTAR")
    cansado = _taxa({"FATIGUE": 0.9, "SILENCE": 0.8}, "INVENTAR")
    assert entediado > 5.0 and cansado < 1.0


def test_curioso_espia_e_de_castigo_nao():
    curioso = _taxa({"WEB": 0.9, "NOVELTY": 0.6, "MOTION": 0.4}, "ESPIAR")
    castigo = _taxa({"PLACA": 0.9, "PRESO": 0.8}, "ESPIAR")
    assert curioso > 2.0 and castigo < 0.5


def test_chance_de_inventar_vem_da_taxa():
    assert chance_de_inventar(0.0) == 0.0 and chance_de_inventar(1e6) == 1.0
    assert 0.0 < chance_de_inventar(5.0) < chance_de_inventar(15.0) < 1.0


def test_espiar_respeita_o_intervalo(monkeypatch):
    monkeypatch.setattr(espiar_ctl.random, "random", lambda: 0.0)          # vontade sempre basta
    e = espiar_ctl.EspiarController(lambda: False)
    assert not e.quer(100.0, 0.016, 0.0)                                   # neurônio quieto: não espia
    assert e.quer(100.0, 0.016, 10.0)
    e.espiou(100.0)
    assert not e.quer(100.0 + e.intervalo() - 1, 0.016, 10.0)
    assert e.quer(100.0 + e.intervalo() + 1, 0.016, 10.0)
    assert espiar_ctl.EspiarController(lambda: True).intervalo() == espiar_ctl.INTERVALO_TESTE_S


# ---------------- no pet ----------------

@pytest.fixture
def pet_app(qapp, tmp_path, monkeypatch):
    from pestinha.app import PestinhaApp
    from pestinha.settings_store import SettingsStore
    paths = Paths(root=tmp_path, dados=tmp_path / "memory")
    pasta = tmp_path / "pets" / "bryan"
    (pasta / "voz").mkdir(parents=True)
    (tmp_path / "pets" / "bryan.json").write_text(json.dumps({"nome": "Bryan", "personalidade": "Você é teste."}))
    (pasta / "recadinhos.txt").write_text("frase já escrita no arquivo\n", encoding="utf-8")
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS, travessuras=True))
    app = PestinhaApp(store, paths)
    from PySide6.QtCore import QObject, Qt, QTimer
    for relogio in app.findChildren(QTimer, options=Qt.FindDirectChildrenOnly):
        relogio.stop()                     # sem os quadros e a rede rodando sozinhos: o teste conduz
    assert isinstance(app.preparo, QObject) and app.preparo.parent() is app
    app.pet.show()
    yield app
    app.preparo.cancelar()
    app.voz.desligar()
    app.floats.hidden_by_tray = True
    for w in list(app.floats.windows.values()):
        w.close()


def _voz_natural(app):
    """Liga a voz natural com dublês: o motor escreve o wav na hora, o sistema só anota o que tocou."""
    referencia = app.conteudo.voz_referencia
    referencia.parent.mkdir(parents=True, exist_ok=True)
    referencia.write_bytes(b"RIFF")
    app.conteudo.voz_referencia_texto.write_text("Oi, eu sou o teste.", encoding="utf-8")
    app.voz.referencia, app.voz.referencia_texto = referencia, app.conteudo.voz_referencia_texto
    app.voz.motor, app.voz.sistema, app.fala.sistema = MotorFalso(), SistemaFalso(), SistemaFalso()
    app.perms["voz"] = True
    return app.voz.motor, app.voz.sistema


def _bilhete(app, inventar_hz):
    from pestinha.world.objetos import NoteThing
    now = time.monotonic()
    acao = app.mischief_ctl._bilhete("bilhete", "ctx", "feliz", {"INVENTAR": inventar_hz}, now, app.bounds(), (0, 0))
    notas = lambda: [t.text for t in app.mischief.things if isinstance(t, NoteThing)]      # noqa: E731
    return acao, notas


def test_rede_quieta_usa_frase_ja_escrita_e_mostra_na_hora(pet_app, tmp_path):
    _instalada_falsa(pet_app.paths.ia_local)
    acao, notas = _bilhete(pet_app, inventar_hz=0.0)
    assert acao == "bilhete" and notas() == ["frase já escrita no arquivo"]
    assert not pet_app.preparo.ocupado()


def test_rede_com_vontade_de_inventar_pede_a_ia(pet_app, qapp, tmp_path, monkeypatch):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("inventei isso agora")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    acao, notas = _bilhete(pet_app, inventar_hz=1000.0)
    assert acao == "bilhete" and pet_app.mischief_ctl.pendente["acao"] == "bilhete_ia" and notas() == []
    # enquanto prepara, ele não apronta outra
    assert pet_app.mischief_ctl.maybe_act(
        time.monotonic(), 1.0, pet_app.bounds(), (0, 0), pet_app.pet.body, motores={"TRAVESSURA": 1e9},
        activity="IDLE", emotion="feliz", perms=pet_app.perms, prof=pet_app.prof, fullscreen=False,
        asleep=False, protest_stage=0) is None
    assert _esperar(qapp, lambda: notas())
    assert notas() == ["inventei isso agora"] and pet_app.mischief_ctl.pendente is None
    assert [ep["acao"] for ep in pet_app.memory.open] == ["bilhete_ia"]      # a memória aprende com a frase nova


def test_sem_permissao_de_inventar_usa_o_arquivo(pet_app, tmp_path):
    _instalada_falsa(pet_app.paths.ia_local)
    pet_app.perms["inventar"] = False
    _acao, notas = _bilhete(pet_app, inventar_hz=1000.0)
    assert notas() == ["frase já escrita no arquivo"]


def test_post_it_espera_a_voz_e_o_audio_some_depois_de_tocar(pet_app, qapp):
    motor, sistema = _voz_natural(pet_app)
    _acao, notas = _bilhete(pet_app, inventar_hz=0.0)
    assert notas() == [] and pet_app.preparo.ocupado()               # ainda gerando a fala
    assert _esperar(qapp, lambda: notas())
    assert motor.pedidos[0]["texto"].endswith("frase já escrita no arquivo")
    assert len(sistema.toques) == 1 and sistema.falas == []          # tocou o áudio preparado, junto
    audio = sistema.toques[0]
    assert audio.exists()
    sistema.processos[-1].parado = True                             # terminou de tocar
    pet_app.voz.recolher()
    assert not audio.exists() and list(pet_app.voz.pasta.glob("*.wav")) == []


def test_ia_e_voz_um_modelo_por_vez(pet_app, qapp, tmp_path, monkeypatch):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("inventei e falei")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    motor, sistema = _voz_natural(pet_app)
    ordem = []
    gerar = motor.gerar
    motor.gerar = lambda pedido, rodar=None: (ordem.append(("voz", chamadas.exists())), gerar(pedido, rodar))[1]
    _acao, notas = _bilhete(pet_app, inventar_hz=1000.0)
    assert _esperar(qapp, lambda: notas())
    assert ordem == [("voz", True)]                                   # a voz só depois que o llama.cpp fechou
    assert notas() == ["inventei e falei"] and len(sistema.toques) == 1


def test_esconderam_no_meio_o_audio_e_apagado(pet_app, qapp):
    motor, sistema = _voz_natural(pet_app)
    _acao, notas = _bilhete(pet_app, inventar_hz=0.0)
    pet_app.perms["bilhetes"] = False
    assert _esperar(qapp, lambda: not pet_app.preparo.ocupado())
    assert notas() == [] and sistema.toques == [] and list(pet_app.voz.pasta.glob("*.wav")) == []
    assert pet_app.mischief_ctl.pendente is None


def test_panico_cancela_o_que_estava_preparando(pet_app, qapp, tmp_path, monkeypatch):
    lento = tmp_path / "lento.py"
    lento.write_text("import time; time.sleep(30)", encoding="utf-8")
    _usar_llama_falso(monkeypatch, [sys.executable, str(lento)])
    _instalada_falsa(pet_app.paths.ia_local)
    _bilhete(pet_app, inventar_hz=1000.0)
    time.sleep(0.2)
    pet_app.panic()
    assert _esperar(qapp, lambda: not pet_app.preparo.ocupado(), tempo=5)
    assert pet_app.mischief_ctl.pendente is None


def _cartaz_fixo(pet_app, monkeypatch, texto="GREVE GERAL!"):
    escolher = pet_app.protest.escolher_cartaz
    monkeypatch.setattr(pet_app.protest, "escolher_cartaz", lambda **kw: dict(escolher(**kw), texto=texto))


def test_cartaz_espera_a_voz_e_aparece_com_ela(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    _cartaz_fixo(pet_app, monkeypatch)
    pr = pet_app.protest
    pr.stage = 1
    pet_app.protest_ctl.on_stage(0, 1)
    pet_app.protest_ctl.carry(pr.respawn_at + 0.1, asleep=False)
    assert pr.sign is None and pet_app.protest_ctl.esperando is not None   # gerando a fala
    assert _esperar(qapp, lambda: pr.sign is not None)
    assert len(motor.pedidos) == 1 and len(sistema.toques) == 1 and sistema.falas == []
    assert motor.pedidos[0]["texto"].endswith(para_fala(pr.sign.text))     # a fala é do cartaz que apareceu


def test_cartaz_sem_nada_para_falar_aparece_na_hora(pet_app, monkeypatch):
    motor, _ = _voz_natural(pet_app)
    _cartaz_fixo(pet_app, monkeypatch, "@#$%@!!!!")
    pr = pet_app.protest
    pr.stage = 1
    pet_app.protest_ctl.on_stage(0, 1)
    pet_app.protest_ctl.carry(pr.respawn_at + 0.1, asleep=False)
    assert pr.sign is not None and not pet_app.preparo.ocupado() and motor.pedidos == []


def test_cartaz_preparado_para_outro_estagio_e_descartado(pet_app, qapp, monkeypatch):
    _voz_natural(pet_app)
    _cartaz_fixo(pet_app, monkeypatch)
    pr = pet_app.protest
    pr.stage = 1
    pet_app.protest_ctl.on_stage(0, 1)
    pet_app.protest_ctl.carry(pr.respawn_at + 0.1, asleep=False)
    pr.stage = 2                                                     # mudou enquanto a voz era gerada
    pet_app.protest_ctl.on_stage(1, 2)
    assert _esperar(qapp, lambda: not pet_app.preparo.ocupado())
    assert pr.sign is None and pr.respawn_at is not None             # o do estágio 2 vem no próximo quadro
    assert list(pet_app.voz.pasta.glob("*.wav")) == []


# ---------------- memes e fotos falam (com a voz ligada) ----------------

def _meme(pet_app, monkeypatch, inventar_hz=0.0):
    """Um meme do Bryan e a travessura dele, com a rede decidindo pela taxa do INVENTAR."""
    pasta = pet_app.conteudo.memes / "feliz"
    pasta.mkdir(parents=True, exist_ok=True)
    _png(pasta / "gato.png", 300, 200)
    monkeypatch.setattr(pet_app.mischief, "_add", _anotar_add(pet_app.mischief))
    plan = pet_app.mischief.plan("meme", "feliz")
    acao = pet_app.mischief_ctl._imagem("meme", plan, "ctx", "feliz", {"INVENTAR": inventar_hz},
                                        time.monotonic(), pet_app.bounds(), (0, 0))
    return acao, plan[1], pasta / "gato.png"


def _anotar_add(engine):
    add = engine._add

    def anotado(thing):
        add(thing)
        engine.apareceram = getattr(engine, "apareceram", []) + [thing]
    return anotado


def test_sem_voz_o_meme_continua_mudo(pet_app, monkeypatch):
    from pestinha.world.objetos import ImageThing
    pet_app.mischief_ctl.pode_falar = lambda: False
    falas = []
    pet_app.mischief.fala_nova.connect(falas.append)
    pasta = pet_app.conteudo.memes / "feliz"
    pasta.mkdir(parents=True, exist_ok=True)
    _png(pasta / "gato.png", 300, 200)
    pet_app.mischief_ctl.pedido_forcado, pet_app.mischief_ctl.forcado_ate = True, time.monotonic() + 5
    monkeypatch.setattr(pet_app.memory, "choose", lambda ctx, options, explore: "meme")
    pet_app.mischief_ctl.postit_weight = 0
    pet_app.pet.body.grounded = True                     # sem a física rodando, ele começa "no ar"
    acao = pet_app.mischief_ctl.maybe_act(
        time.monotonic(), 0.016, pet_app.bounds(), (0, 0), pet_app.pet.body, motores={"TRAVESSURA": 0.0},
        activity="IDLE", emotion="feliz", perms=dict(pet_app.perms, memes=True), prof=pet_app.prof,
        fullscreen=False, asleep=False, protest_stage=0)
    assert acao == "meme" and falas == []
    assert any(isinstance(t, ImageThing) and t.fala is None for t in pet_app.mischief.things)


def test_com_a_voz_do_sistema_o_meme_fala_uma_reacao_ao_aparecer(pet_app, monkeypatch):
    (pet_app.conteudo.falas_memes).write_text("olha esse gato.\n", encoding="utf-8")
    pet_app.voz.sistema = SistemaFalso()
    pet_app.perms["voz"] = True
    acao, meme, _arquivo = _meme(pet_app, monkeypatch)
    assert acao == "meme" and meme in pet_app.mischief.things and meme.fala == "olha esse gato."
    assert pet_app.voz.sistema.falas == [("olha esse gato.", None)] and not pet_app.preparo.ocupado()


def test_com_a_voz_natural_o_meme_espera_a_fala_e_o_original_fica(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    acao, meme, arquivo = _meme(pet_app, monkeypatch)
    assert acao == "meme" and meme not in pet_app.mischief.things and pet_app.preparo.ocupado()
    assert _esperar(qapp, lambda: meme in pet_app.mischief.things)
    assert len(motor.pedidos) == 1 and len(sistema.toques) == 1 and sistema.falas == []
    assert arquivo.exists() and [ep["acao"] for ep in pet_app.memory.open] == ["meme"]


def test_a_rede_com_vontade_de_inventar_faz_a_ia_comentar_o_meme(pet_app, qapp, tmp_path, monkeypatch):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("esse gato tem mais mindset que eu")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    motor, sistema = _voz_natural(pet_app)
    _acao, meme, arquivo = _meme(pet_app, monkeypatch, inventar_hz=1000.0)
    assert _esperar(qapp, lambda: meme in pet_app.mischief.things)
    assert meme.fala == "esse gato tem mais mindset que eu" and len(sistema.toques) == 1
    linha = chamadas.read_text(encoding="utf-8")
    assert "--image" in linha and str(arquivo) not in linha            # a IA olhou uma cópia...
    assert arquivo.exists()                                            # ...e o meme do pet continua lá
    assert not pet_app.paths.ultima_espiada.exists()                   # não é print da tela


def test_se_a_ia_nao_comenta_o_meme_aparece_com_reacao_ja_escrita(pet_app, qapp, tmp_path, monkeypatch):
    prog, _ = llama_falso(tmp_path, ["quebrou"], codigo=2)
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    pet_app.voz.sistema = SistemaFalso()
    pet_app.perms["voz"] = True
    _acao, meme, _arquivo = _meme(pet_app, monkeypatch, inventar_hz=1000.0)
    assert _esperar(qapp, lambda: meme in pet_app.mischief.things)
    assert meme.fala and pet_app.mischief_ctl.pendente is None


def test_meme_preparado_com_bilhetes_desligados_aparece(pet_app, qapp, monkeypatch):
    _voz_natural(pet_app)
    pet_app.perms["bilhetes"] = False                                  # o meme não depende dos bilhetes
    _acao, meme, _arquivo = _meme(pet_app, monkeypatch)
    assert _esperar(qapp, lambda: meme in pet_app.mischief.things)


def test_meme_cancelado_no_meio_nao_aparece_e_libera(pet_app, qapp, monkeypatch):
    _voz_natural(pet_app)
    _acao, meme, _arquivo = _meme(pet_app, monkeypatch)
    apagados = []
    monkeypatch.setattr(meme, "deleteLater", lambda: apagados.append(meme))
    pet_app.preparo.cancelar()
    assert _esperar(qapp, lambda: pet_app.mischief_ctl.pendente is None)
    assert meme not in pet_app.mischief.things and apagados == [meme]


def test_revolucao_fala_como_palavra_de_ordem_e_para_quando_o_cartaz_sai(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    _cartaz_fixo(pet_app, monkeypatch, "MINHA BOLINHA AGORA É UM NFT.")
    pr = pet_app.protest
    pr.stage = 4
    pet_app.protest_ctl.on_stage(3, 4)
    pet_app.protest_ctl.carry(pr.respawn_at + 0.1, asleep=False)
    assert _esperar(qapp, lambda: pr.sign is not None)
    pedido = motor.pedidos[0]
    assert pedido["texto"] == "[dissatisfaction-hnn] minha bolinha agora é um nft!"   # uma vez, sem dobrar
    assert pedido["volume"] > 0.5 and pedido["velocidade"] < 1.0
    assert pet_app.voz._repetir is not None                                # vai repetir depois da pausa...
    pet_app.protest_ctl.drop_sign()
    assert pet_app.voz._repetir is None                                    # ...mas o cartaz saiu: não repete
    pet_app.perms.update(repetir_vezes=3, repetir_pausa_ms=250)            # as Configurações valem na hora
    assert pet_app.voz.repeticao() == (3, 0.25)
    assert {1: "bravo", 2: "bravo", 3: "grevista", 4: "revoltado", 0: None} == {
        e: (setattr(pr, "stage", e), pet_app.emocao_do_protesto())[1] for e in (1, 2, 3, 4, 0)}


# ---------------- botão "Testar meme" (Configurações) ----------------

def _pasta_de_memes(pet_app):
    pasta = pet_app.conteudo.memes / "feliz"
    pasta.mkdir(parents=True, exist_ok=True)
    _png(pasta / "gato.png", 300, 200)
    pet_app.pet.body.grounded = True                     # sem a física rodando, ele começa "no ar"
    return pasta / "gato.png"


def _memes_na_tela(pet_app):
    from pestinha.world.objetos import ImageThing
    return [t for t in pet_app.mischief.things if isinstance(t, ImageThing)]


def test_testar_meme_com_a_voz_natural_espera_a_fala_e_nao_ensina_a_rede(pet_app, qapp):
    motor, sistema = _voz_natural(pet_app)
    _pasta_de_memes(pet_app)
    aviso = pet_app.testar_meme()
    assert "gato.png" in aviso and "prepara a fala" in aviso and not _memes_na_tela(pet_app)
    assert "preparando outra coisa" in pet_app.testar_meme()            # um por vez
    assert _esperar(qapp, lambda: _memes_na_tela(pet_app))
    assert len(motor.pedidos) == 1 and len(sistema.toques) == 1
    assert pet_app.memory.open == []                     # teste: não vira episódio para a rede aprender


def test_testar_meme_com_ia(pet_app, qapp, tmp_path, monkeypatch):
    prog, _ = llama_falso(tmp_path, [resposta_qwen("esse gato é meu chefe")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    _voz_natural(pet_app)
    _pasta_de_memes(pet_app)
    assert "IA está olhando" in pet_app.testar_meme(com_ia=True)
    assert _esperar(qapp, lambda: _memes_na_tela(pet_app))
    assert _memes_na_tela(pet_app)[0].fala == "esse gato é meu chefe"


def test_testar_meme_sem_voz_traz_calado(pet_app):
    pet_app.perms["voz"] = False
    _pasta_de_memes(pet_app)
    aviso = pet_app.testar_meme()
    assert "calado" in aviso and len(_memes_na_tela(pet_app)) == 1 and _memes_na_tela(pet_app)[0].fala is None


def test_testar_meme_explica_quando_nao_da(pet_app):
    assert "Não há memes" in pet_app.testar_meme()
    _pasta_de_memes(pet_app)
    pet_app.castigo.dentro = True
    assert "castigo" in pet_app.testar_meme()
    pet_app.castigo.dentro = False
    pet_app.pet.hide()
    assert "escondido" in pet_app.testar_meme()
    assert not _memes_na_tela(pet_app)


def test_botao_das_configuracoes_traz_o_meme_e_mostra_o_aviso(pet_app):
    pet_app.perms.update(travessuras=True, memes=True, voz=False)
    _pasta_de_memes(pet_app)
    pet_app.open_settings()
    pet_app.settings.botao_meme.click()
    assert len(_memes_na_tela(pet_app)) == 1 and "gato.png" in pet_app.settings.teste_status.text()
    pet_app.settings.close()


def test_configuracoes_tem_os_botoes_de_teste(pet_app, monkeypatch):
    from pestinha.ui.ui import SettingsDialog
    perms = dict(pet_app.perms, travessuras=True, memes=True, voz=True, inventar=True)
    d = SettingsDialog(perms, pet_app.paths, first_run=False)
    pedidos = []
    d.testar_meme.connect(pedidos.append)
    assert d.botao_meme.isEnabled() and not d.botao_meme_ia.isEnabled()      # sem a IA instalada
    d.botao_meme.click()
    assert pedidos == [False] and d.teste_status.text()
    d.aviso_teste("Trouxe gato.png.")
    assert d.teste_status.text() == "Trouxe gato.png."
    d.boxes["memes"].setChecked(False)
    assert not d.botao_meme.isEnabled()
    d.set_active(False)                                                      # pânico
    d.boxes["memes"].setChecked(True)
    assert not d.botao_meme.isEnabled()
    d.close()
    primeira = SettingsDialog(perms, pet_app.paths, first_run=True)          # o pet ainda não abriu
    assert primeira.botao_meme.isHidden() and primeira.botao_meme_ia.isHidden()
    primeira.close()


# ---------------- cantinho do castigo fala ----------------

def test_xingamento_e_censurado_na_fala():
    from pestinha.mind.castigo_ctl import fala_do_cartaz
    assert fala_do_cartaz("ISSO NÃO É JUSTO.", ("argh!",)) == "ISSO NÃO É JUSTO."
    assert fala_do_cartaz("#@$%&... SINERGIA!", ("argh!",)) == "piii... SINERGIA!"
    assert fala_do_cartaz("@!#$% DE MERCADO!!", ("argh!",)) == "piii DE MERCADO!!"
    assert fala_do_cartaz("@#$%@!!!!", ("argh!",)) == "argh!"          # só símbolos: resmunga
    assert fala_do_cartaz("@!#%$...", ()) == "piii!"


def _castigo(pet_app, monkeypatch):
    """Ele preso no cantinho, com cartazes conhecidos e o sorteio fixo (sempre cola, sempre o primeiro)."""
    from types import SimpleNamespace
    from pestinha.mind import castigo_ctl
    pet_app.conteudo.signs.write_text("[castigo]\nISSO NÃO É JUSTO.\n[xingamento]\n@#$%@!!!!\n"
                                      "[resmungo]\nargh, que raiva!\n", encoding="utf-8")
    monkeypatch.setattr(castigo_ctl, "random", SimpleNamespace(random=lambda: 0.0, choice=lambda s: s[0]))
    c = pet_app.castigo
    c.ativo, c.dentro, c.ultimo = True, True, time.monotonic()
    return c


def _colar(pet_app, c, bravo):
    c._decidir(time.monotonic(), 0.1, pet_app.pet.body, pet_app.bounds(),
               {"CARTAZ": 100.0, "ANGRY": 50.0 if bravo else 0.0})


def test_cantinho_espera_a_voz_natural_e_cola_o_cartaz_falando(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    c = _castigo(pet_app, monkeypatch)
    _colar(pet_app, c, bravo=False)
    assert c.cartaz is None and c.esperando is not None                    # gerando a fala
    _colar(pet_app, c, bravo=False)                                        # um cartaz por vez: este não entra
    assert _esperar(qapp, lambda: c.cartaz is not None)
    assert len(motor.pedidos) == 1 and c.esperando is None
    assert c.cartaz.text == "ISSO NÃO É JUSTO." and motor.pedidos[0]["texto"].startswith("[sigh]")  # drama
    assert len(sistema.toques) == 1 and sistema.falas == []


def test_cantinho_bravo_xinga_censurado(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    c = _castigo(pet_app, monkeypatch)
    _colar(pet_app, c, bravo=True)
    assert _esperar(qapp, lambda: c.cartaz is not None)
    assert c.cartaz.text == "@#$%@!!!!"                                    # a placa xinga em símbolos...
    assert motor.pedidos[0]["texto"] == "[dissatisfaction-hnn] argh, que raiva!"   # ...e ele resmunga
    assert len(sistema.toques) == 1


def test_cantinho_com_a_voz_do_sistema_fala_na_hora(pet_app, monkeypatch):
    pet_app.voz.sistema = SistemaFalso()
    pet_app.perms["voz"] = True
    c = _castigo(pet_app, monkeypatch)
    _colar(pet_app, c, bravo=False)
    assert c.cartaz is not None and pet_app.voz.sistema.falas == [("isso não é justo.", None)]


def test_saiu_do_cantinho_no_meio_o_cartaz_nao_aparece(pet_app, qapp, monkeypatch):
    motor, sistema = _voz_natural(pet_app)
    c = _castigo(pet_app, monkeypatch)
    _colar(pet_app, c, bravo=False)
    c._soltar(pet_app.pet_state)                                           # tiraram ele do canto
    assert _esperar(qapp, lambda: not pet_app.preparo.ocupado())
    assert c.cartaz is None and c.esperando is None and sistema.toques == []
    assert not list(pet_app.voz.pasta.glob("*.wav*"))                      # o áudio foi apagado


def test_espiar_precisa_de_permissao(pet_app, monkeypatch):
    _instalada_falsa(pet_app.paths.ia_local)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.permissao_tela", lambda: True)
    assert not pet_app.pode_espiar()                                  # "Espiar a tela" vem desligado
    pet_app.perms["ver_tela"] = True
    assert pet_app.pode_espiar()
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.permissao_tela", lambda: False)
    assert not pet_app.pode_espiar()                                  # o sistema não deixou
    assert config.DEFAULT_PERMISSIONS["ver_tela"] is False and config.DEFAULT_PERMISSIONS["inventar"] is True


def test_espiar_comenta_a_tela_e_apaga_o_print(pet_app, qapp, tmp_path, monkeypatch):
    from pestinha.world.objetos import NoteThing
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("você está programando de novo?")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    prints = []

    def capturar(destino):
        prints.append(Path(destino))
        _png(destino, 800, 600)
        return True
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.permissao_tela", lambda: True)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.CAPTURA_EM_QUALQUER_THREAD", True)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.capturar_tela", capturar)
    monkeypatch.setattr(espiar_ctl.random, "random", lambda: 0.0)
    pet_app.perms["ver_tela"] = True
    pet_app.fullscreen = False
    pet_app.maybe_espiar(time.monotonic(), 0.016, {"ESPIAR": 50.0})
    assert _esperar(qapp, lambda: any(isinstance(t, NoteThing) for t in pet_app.mischief.things))
    assert [t.text for t in pet_app.mischief.things] == ["você está programando de novo?"]
    assert "--image" in chamadas.read_text(encoding="utf-8") and not prints[0].exists()
    assert pet_app.espiar.descansando(time.monotonic())                # a próxima, só depois do intervalo


def _espiar_com_print(pet_app, qapp, tmp_path, monkeypatch, modo_teste):
    prog, _ = llama_falso(tmp_path, [resposta_qwen("que tela branca, hein")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.permissao_tela", lambda: True)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.CAPTURA_EM_QUALQUER_THREAD", True)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.capturar_tela", lambda d: (_png(d, 2560, 1600), True)[1])
    pet_app.perms["modo_teste"] = modo_teste
    pet_app.menu_espiar()
    assert _esperar(qapp, lambda: pet_app.mischief.things)


def test_modo_teste_guarda_o_ultimo_print_para_conferir(pet_app, qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    _espiar_com_print(pet_app, qapp, tmp_path, monkeypatch, modo_teste=True)
    copia = pet_app.paths.ultima_espiada
    assert copia.exists() and QImage(str(copia)).width() == 1280            # o print que a IA olhou
    assert copia.parent == pet_app.paths.log.parent
    itens = _menu_do_pet(pet_app, monkeypatch)
    assert "Ver o último print (teste)" in itens
    pet_app.apply_perms(dict(pet_app.perms, modo_teste=False))              # saiu do Modo teste: some
    assert not copia.exists()


def test_fora_do_modo_teste_o_print_nao_fica_em_lugar_nenhum(pet_app, qapp, tmp_path, monkeypatch):
    _espiar_com_print(pet_app, qapp, tmp_path, monkeypatch, modo_teste=False)
    assert not pet_app.paths.ultima_espiada.exists()
    assert "Ver o último print (teste)" not in _menu_do_pet(pet_app, monkeypatch)


def _menu_do_pet(pet_app, monkeypatch):
    from PySide6.QtWidgets import QMenu
    vistos = []

    class MenuAnotado(QMenu):
        def exec(self, *_a):
            vistos.append([acao.text() for acao in self.actions() if acao.text()])

    monkeypatch.setattr("pestinha.controle.interacao.QMenu", MenuAnotado)
    pet_app.show_pet_menu(None)
    return vistos[-1]


def test_espiar_pelo_menu_sem_permissao_do_sistema_pede_e_avisa(pet_app, monkeypatch):
    pedidos, avisos = [], []
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.permissao_tela", lambda: False)
    monkeypatch.setattr("pestinha.controle.interacao.plataforma.pedir_permissao_tela", lambda: pedidos.append(1))
    monkeypatch.setattr(pet_app.tray.icon, "showMessage", lambda *a: avisos.append(a[1]))
    pet_app.menu_espiar()
    assert pedidos == [1] and "Gravação de Tela" in avisos[0] and not pet_app.preparo.ocupado()


def test_configuracoes_tem_as_opcoes_da_ia_local(qapp, tmp_path):
    from pestinha.ui.ui import SettingsDialog
    paths = Paths(root=tmp_path, dados=tmp_path / "memory")
    perms = dict(config.DEFAULT_PERMISSIONS, travessuras=True)
    dialogo = SettingsDialog(perms, paths)
    assert dialogo.boxes["inventar"].isEnabled() and dialogo.boxes["ver_tela"].isEnabled()
    assert "não instalada" in dialogo.ia_status.text()
    dialogo.boxes["bilhetes"].setChecked(False)
    assert not dialogo.boxes["inventar"].isEnabled() and not dialogo.boxes["ver_tela"].isEnabled()
    dialogo.close()
