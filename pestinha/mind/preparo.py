"""
PREPARO - o trabalho pesado antes de algo aparecer na tela: escrever com a IA local e gerar a fala.

Uma tarefa por vez, numa fila, numa thread só. Cada passo abre um programa que carrega o modelo, faz a
sua parte e fecha (a memória volta na hora):

    escrever (opcional)   llama.cpp: carrega o Qwen, escreve a frase, fecha
    falar (opcional)      OmniVoice: carrega a voz, gera o áudio da frase, fecha
    mostrar               de volta na tela: o post-it (ou cartaz) aparece junto com o áudio

Como um passo só começa depois que o anterior fechou, os dois modelos nunca ficam na memória juntos.

Nada de Qt na thread de trabalho: ela só roda programas (subprocess) e devolve o resultado numa fila,
que um QTimer da tela esvazia. Quem pediu é chamado na thread da tela.

    pedir(tarefa)     põe na fila (devolve False se a fila estiver cheia)
    cancelar()        pânico, fechar, trocar a voz: mata o programa da vez e esquece a fila
"""

import collections
import queue
import subprocess
import threading

from PySide6.QtCore import QObject, QTimer

from ..log import log

MAX_FILA = 4                # tarefas esperando (contando a da vez): mais que isso, recusa
INTERVALO_MS = 100          # de quanto em quanto tempo a tela confere se algo ficou pronto


class Cancelada(Exception):
    """A tarefa foi cancelada no meio (pânico, fechar o programa)."""


class Controle:
    """Por onde a tarefa abre programas: guarda o da vez, para dar para cancelar."""

    def __init__(self):
        self._trava = threading.Lock()
        self._processo = None
        self.cancelada = False

    def rodar(self, cmd, entrada=None, tempo=60.0, erros=subprocess.PIPE, ambiente=None):
        """Roda `cmd` até o fim (ou até `tempo`). Levanta Cancelada, RuntimeError (tempo) ou OSError."""
        with self._trava:
            if self.cancelada:
                raise Cancelada()
            processo = subprocess.Popen(cmd, stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=erros, env=ambiente)
            self._processo = processo
        try:
            saida, erro = processo.communicate(entrada, timeout=tempo)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.communicate()
            raise RuntimeError(f"passou de {tempo:.0f} s") from None
        finally:
            with self._trava:
                self._processo = None
        if self.cancelada:
            raise Cancelada()
        return subprocess.CompletedProcess(cmd, processo.returncode, saida, erro)

    def cancelar(self):
        """Mata o programa da vez; os próximos nem começam."""
        with self._trava:
            self.cancelada = True
            processo = self._processo
        if processo is not None and processo.poll() is None:
            try:
                processo.kill()
            except OSError:
                pass


class Tarefa:
    """
    Uma coisa a preparar.
        trabalho(controle) -> resultado   roda na thread (abre programas pelo controle)
        ao_terminar(resultado)            na tela, quando ficou pronto
        ao_falhar(motivo)                 na tela, se deu errado
        descartar(resultado)              se ficou pronto mas foi cancelado: limpa (apaga o áudio)
        ao_cancelar()                     na tela, se foi cancelada (na fila, no meio ou já pronta)
    """

    def __init__(self, rotulo, trabalho, ao_terminar, ao_falhar=None, descartar=None, ao_cancelar=None):
        self.rotulo = rotulo
        self.trabalho = trabalho
        self.ao_terminar = ao_terminar
        self.ao_falhar = ao_falhar
        self.descartar = descartar
        self.ao_cancelar = ao_cancelar


class Preparo(QObject):
    """A fila de tarefas pesadas: uma por vez, fora da tela."""

    def __init__(self, parent=None, max_fila=MAX_FILA):
        super().__init__(parent)
        self.max_fila = max_fila
        self._trava = threading.Condition()
        self._fila = collections.deque()
        self._prontas = queue.SimpleQueue()
        self._atual = None              # (tarefa, controle) rodando agora
        self._vez = 0                   # cancelar() muda a vez: o que era da vez antiga é descartado
        self._thread = None
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVALO_MS)
        self._timer.timeout.connect(self._entregar)

    # ---------------- na tela ----------------

    def pedir(self, tarefa):
        """Põe a tarefa na fila. False se a fila estiver cheia."""
        with self._trava:
            if len(self._fila) + (self._atual is not None) >= self.max_fila:
                return False
            self._fila.append((self._vez, tarefa))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._laco, name="preparo", daemon=True)
                self._thread.start()
            self._trava.notify()
        if not self._timer.isActive():
            self._timer.start()
        return True

    def ocupado(self):
        """Tem alguma tarefa na fila, rodando ou esperando a tela."""
        with self._trava:
            return bool(self._fila) or self._atual is not None or not self._prontas.empty()

    def rotulos(self):
        """O que está na fila (a da vez primeiro), para o menu e o log."""
        with self._trava:
            atual = [self._atual[0].rotulo] if self._atual else []
            return atual + [t.rotulo for _vez, t in self._fila]

    def cancelar(self):
        """Esquece a fila e mata o programa da vez. O que já ficou pronto é descartado."""
        with self._trava:
            self._vez += 1
            esperando = [t for _vez, t in self._fila]
            self._fila.clear()
            atual = self._atual
        if atual is not None:
            atual[1].cancelar()
        for tarefa in esperando:
            self._avisar_cancelada(tarefa)
        self._entregar()

    @staticmethod
    def _avisar_cancelada(tarefa):
        if tarefa.ao_cancelar is not None:
            try:
                tarefa.ao_cancelar()
            except Exception as erro:
                log(f"[preparo] {tarefa.rotulo}: erro ao cancelar: {erro}")

    # ---------------- na thread ----------------

    def _laco(self):
        """Pega a próxima tarefa e roda; nunca duas ao mesmo tempo."""
        while True:
            with self._trava:
                while not self._fila:
                    self._trava.wait()
                vez, tarefa = self._fila.popleft()
                controle = Controle()
                if vez != self._vez:
                    continue
                self._atual = (tarefa, controle)
            try:
                saida = ("pronta", tarefa.trabalho(controle))
            except Cancelada:
                saida = ("cancelada", None)
            except Exception as erro:              # um defeito na tarefa não pode derrubar a fila
                saida = ("falhou", str(erro) or type(erro).__name__)
            with self._trava:
                self._prontas.put((vez, tarefa, saida))
                self._atual = None

    # ---------------- de volta na tela ----------------

    def _entregar(self):
        """(Timer) Chama quem pediu, na tela. Para o timer quando não há mais nada."""
        while True:
            try:
                vez, tarefa, (estado, valor) = self._prontas.get_nowait()
            except queue.Empty:
                break
            try:
                if vez != self._vez or estado == "cancelada":
                    if estado == "pronta" and tarefa.descartar is not None:
                        tarefa.descartar(valor)
                    self._avisar_cancelada(tarefa)
                elif estado == "pronta":
                    tarefa.ao_terminar(valor)
                elif tarefa.ao_falhar is not None:
                    tarefa.ao_falhar(valor)
                else:
                    log(f"[preparo] {tarefa.rotulo}: {valor}")
            except Exception as erro:               # quem pediu errou: registra e segue com as outras
                log(f"[preparo] {tarefa.rotulo}: erro ao entregar: {erro}")
        if not self.ocupado():
            self._timer.stop()
