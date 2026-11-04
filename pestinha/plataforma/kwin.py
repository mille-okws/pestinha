"""
KDE Plasma 6 no Wayland: as janelas do pet rodam pelo XWayland (main.py) e os sentidos vêm do KWin.

O Wayland não deixa um programa ver as outras janelas nem o cursor. Um script do KWin (kwin_ponte.js)
manda isso por DBus; o tempo ocioso vem do protocolo ext-idle-notify-v1 (pywayland). Só geometria,
pid e estado das janelas; nunca títulos. Sem o KWin ou sem pywayland, a leitura vira o valor padrão.
"""

import atexit
import json
import math
import os
import time
from pathlib import Path

import psutil
from PySide6.QtCore import ClassInfo, QCoreApplication, QObject, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from ..log import log
from . import linux

SERVICO, CAMINHO, INTERFACE = "io.github.pestinha", "/ponte", "io.github.pestinha.Ponte"
NOME_DO_SCRIPT = "pestinha"
SCRIPT = Path(__file__).with_name("kwin_ponte.js")
sem_foco_nativo = linux.sem_foco_nativo     # igual ao X11: as janelas do pet rodam pelo XWayland
LIMIAR_OCIOSO = 0.3       # igual ao limiar de "digitando" (senses e app): sem aviso = input nos últimos 0,3 s

_recebido = {"estado": None, "cursor": None}
_atalho = []              # callback do atalho, quando registrado
_ponte = None             # None: não tentou; False: falhou; senão (objeto exportado, interface do KWin)
_ocioso = None            # None: não tentou; False: falhou; senão _Ocioso


def _janela(dados):
    """Uma janela da ponte, validada (o DBus é aberto a qualquer programa local), ou None."""
    try:
        x, y, w, h = (float(dados[k]) for k in ("x", "y", "w", "h"))
        pid = int(dados["pid"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        return None
    return {"id": str(dados.get("id")), "pid": pid, "ret": (x, y, x + w, y + h),
            "max": dados.get("max") is True, "cheia": dados.get("cheia") is True}


def parse_estado(texto):
    """(janelas de cima para baixo, janela ativa ou None) a partir do JSON da ponte; vazio se malformado."""
    try:
        dados = json.loads(texto)
    except (TypeError, ValueError):
        return [], None
    if not isinstance(dados, dict):
        return [], None
    lista = dados.get("janelas")
    janelas = [j for j in map(_janela, lista if isinstance(lista, list) else []) if j is not None]
    return janelas, (_janela(dados["ativa"]) if dados.get("ativa") is not None else None)


def parse_cursor(texto):
    """(x, y) a partir de "[x, y]", ou None se malformado."""
    try:
        x, y = (float(v) for v in json.loads(texto))
    except (TypeError, ValueError, OverflowError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def segundos_ocioso(desde, agora):
    """Tempo ocioso: o compositor avisa LIMIAR_OCIOSO depois do último toque, então soma o limiar."""
    return 0.0 if desde is None else agora - desde + LIMIAR_OCIOSO


@ClassInfo({"D-Bus Interface": INTERFACE})
class _Ponte(QObject):
    """O que o script do KWin chama. Só guarda o texto: quem lê valida na hora de usar."""

    @Slot(str)
    def estado(self, texto):
        _recebido["estado"] = texto

    @Slot(str)
    def cursor(self, texto):
        _recebido["cursor"] = texto

    @Slot(result=int)
    def pid(self):
        return os.getpid()

    @Slot()
    def atalho(self):
        for callback in _atalho:
            callback()


def _iniciar_ponte():
    """Exporta a ponte no DBus e carrega o script no KWin; devolve (ponte, kwin) ou None."""
    barramento = QDBusConnection.sessionBus()
    ponte = _Ponte()
    if not (barramento.registerService(SERVICO)
            and barramento.registerObject(CAMINHO, ponte, QDBusConnection.ExportAllSlots)):
        log(f"[kwin] não deu para registrar {SERVICO} no DBus: {barramento.lastError().message()}")
        return None
    kwin = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", barramento)
    kwin.call("unloadScript", NOME_DO_SCRIPT)         # sobra de uma execução que não fechou direito
    resposta = kwin.call("loadScript", str(SCRIPT), NOME_DO_SCRIPT)
    if resposta.type() == QDBusMessage.ErrorMessage or not resposta.arguments() or resposta.arguments()[0] < 0:
        log(f"[kwin] o KWin não carregou {SCRIPT.name}: {resposta.errorMessage()}")
        return None
    kwin.call("start")
    QCoreApplication.instance().aboutToQuit.connect(lambda: kwin.call("unloadScript", NOME_DO_SCRIPT))
    log("[kwin] ponte ligada: janelas, cursor e atalho vêm do KWin")
    return ponte, kwin


def _ligada():
    """Liga a ponte na primeira leitura (o DBus do Qt precisa do QApplication já criado)."""
    global _ponte
    if _ponte is None and QCoreApplication.instance() is not None:
        _ponte = _iniciar_ponte() or False
    return bool(_ponte)


def _estado():
    return parse_estado(_recebido["estado"]) if _ligada() else ([], None)


class _Ocioso:
    """Conexão própria com o compositor, só para o aviso de ocioso (o Qt fala com o XWayland)."""

    def __init__(self):
        from pywayland.client import Display
        from pywayland.protocol.ext_idle_notify_v1 import ExtIdleNotifierV1
        from pywayland.protocol.wayland import WlSeat

        self.desde = None
        self.display = Display()
        self.display.connect()
        registro, globais = self.display.get_registry(), {}
        registro.dispatcher["global"] = lambda _r, nome, interface, _v: globais.setdefault(interface, nome)
        self.display.roundtrip()
        seat = registro.bind(globais["wl_seat"], WlSeat, 1)
        avisador = registro.bind(globais["ext_idle_notifier_v1"], ExtIdleNotifierV1, 1)
        self.aviso = avisador.get_idle_notification(int(LIMIAR_OCIOSO * 1000), seat)
        self.aviso.dispatcher["idled"] = lambda _a: setattr(self, "desde", time.monotonic())
        self.aviso.dispatcher["resumed"] = lambda _a: setattr(self, "desde", None)
        atexit.register(self.fechar)                 # sem isso o Python derruba o pywayland fora de ordem e dá segfault

    def fechar(self):
        self.aviso.destroy()
        self.display.disconnect()

    def segundos(self):
        self.display.roundtrip()                     # lê os avisos pendentes (ida e volta curta ao compositor)
        return segundos_ocioso(self.desde, time.monotonic())


def ocioso_segundos():
    """Tempo ocioso pelo ext-idle-notify-v1. Sem pywayland ou sem o protocolo, devolve 0 (sempre ativo)."""
    global _ocioso
    if _ocioso is None:
        try:
            _ocioso = _Ocioso()
        except Exception as erro:
            log(f"[kwin] tempo ocioso indisponível ({erro!r}): fica como se você estivesse sempre ativo")
            _ocioso = False
    if not _ocioso:
        return 0.0
    try:
        return _ocioso.segundos()
    except Exception as erro:
        log(f"[kwin] a conexão do tempo ocioso caiu ({erro!r})")
        _ocioso = False
        return 0.0


def processo_ativo():
    """Nome do programa da janela ativa, pelo pid que o KWin informa."""
    ativa = _estado()[1]
    try:
        return psutil.Process(ativa["pid"]).name().lower() if ativa else "unknown"
    except (ValueError, psutil.Error):
        return "unknown"


def retangulo_ativo(escala=1.0):
    """Retângulo da janela ativa em pixels físicos (o KWin fala em pixels lógicos), ou None."""
    ativa = _estado()[1]
    return tuple(v * escala for v in ativa["ret"]) if ativa else None


def tela_cheia():
    """Diz se a janela ativa está em tela cheia (o KWin sabe, em qualquer monitor)."""
    ativa = _estado()[1]
    return bool(ativa and ativa["cheia"])


def janelas_visiveis(excluir, escala=1.0):
    """Janelas visíveis de outros programas, de cima para baixo (sem as do próprio pet, pelo pid)."""
    meu_pid = os.getpid()
    return [(j["id"], tuple(v * escala for v in j["ret"]), j["max"]) for j in _estado()[0]
            if j["pid"] != meu_pid and j["ret"][2] - j["ret"][0] >= linux.LARGURA_MINIMA
            and j["ret"][3] - j["ret"][1] >= linux.ALTURA_MINIMA]


def cursor():
    """Cursor em pixels lógicos, visto pelo KWin (sobre qualquer janela), ou None se a ponte não ligou."""
    # shortcut: supõe a mesma escala em todos os monitores (Qt pelo XWayland usa uma só); com escalas mistas, converter por tela
    return parse_cursor(_recebido["cursor"]) if _ligada() and _recebido["cursor"] else None


def iniciar_atalho(callback):
    """Ctrl+Alt+Shift+B registrado pelo script do KWin (o pynput não ouve janelas nativas do Wayland)."""
    if not _ligada():
        return False
    _atalho.append(callback)
    return True
