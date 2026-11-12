"""
MOTOR DA VOZ NATURAL - abre o trabalhador do OmniVoice (mind/omnivoice_trabalhador.py) e conversa com ele.

O trabalhador roda com o Python de voz_natural/ambiente (onde estão o torch e o OmniVoice), num
processo separado: o Pestinha não depende do torch e continua leve para quem não instalou a voz.
A conversa é por linhas de JSON na entrada e na saída padrão (nenhuma porta de rede é aberta).

    estado      "desligado" -> "carregando" -> "pronto"; "falhou" se o processo morrer sozinho
    ligar()     abre o processo (o modelo leva alguns segundos para carregar; os pedidos esperam na fila)
    pedir(p, f) manda um pedido; `f(resposta)` é chamada na thread de leitura quando ele responder
    desligar()  fecha a entrada (o trabalhador sai sozinho) e, se demorar, encerra o processo
"""

import itertools
import json
import subprocess
import sys
import threading
from pathlib import Path

from ..log import log

TRABALHADOR = Path(__file__).with_name("omnivoice_trabalhador.py")


def python_do_ambiente(pasta):
    """O Python do ambiente da voz natural (voz_natural/ambiente)."""
    ambiente = Path(pasta) / "ambiente"
    if sys.platform == "win32":
        return ambiente / "Scripts" / "python.exe"
    return ambiente / "bin" / "python"


def instalada(pasta):
    """Diz se a voz natural está instalada e completa (o instalador grava instalado.json no fim)."""
    pasta = Path(pasta)
    return ((pasta / "instalado.json").exists() and python_do_ambiente(pasta).exists()
            and (pasta / "modelo" / "model.safetensors").exists())


class MotorVoz:
    """Processo do trabalhador do OmniVoice, com a fila de pedidos esperando resposta."""

    def __init__(self, pasta, log_arquivo=None, python=None, trabalhador=TRABALHADOR):
        """`pasta` é voz_natural/; `log_arquivo` recebe o que o trabalhador escreve no stderr."""
        self.pasta = Path(pasta)
        self.log_arquivo = Path(log_arquivo) if log_arquivo else None
        self.python = Path(python) if python else None        # só os testes trocam
        self.trabalhador = Path(trabalhador)
        self.estado = "desligado"
        self.dispositivo = None
        self._processo = None
        self._pendentes = {}
        self._ids = itertools.count(1)
        self._trava = threading.Lock()
        self._desligando = False

    def instalado(self):
        """Diz se dá para ligar (os testes, com `python` próprio, não precisam da instalação)."""
        return self.python is not None or instalada(self.pasta)

    def rodando(self):
        """Carregando ou pronto: aceita pedidos."""
        return self.estado in ("carregando", "pronto")

    def ligar(self):
        """Abre o trabalhador, se a voz natural estiver instalada e ele ainda não estiver aberto."""
        with self._trava:
            if self.rodando() or not self.instalado():
                return self.rodando()
            python = self.python or python_do_ambiente(self.pasta)
            erros = subprocess.DEVNULL
            if self.log_arquivo is not None:
                try:
                    self.log_arquivo.parent.mkdir(parents=True, exist_ok=True)
                    erros = open(self.log_arquivo, "a", encoding="utf-8")
                except OSError:
                    erros = subprocess.DEVNULL
            try:
                self._processo = subprocess.Popen(
                    [str(python), "-u", str(self.trabalhador), "--modelo", str(self.pasta / "modelo")],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=erros,
                    text=True, encoding="utf-8", bufsize=1)
            except OSError as erro:
                log(f"[voz] não abriu o motor da voz natural: {erro}")
                self.estado = "falhou"
                return False
            finally:
                if erros is not subprocess.DEVNULL:
                    erros.close()                          # o processo filho já tem a cópia dele
            self._desligando = False
            self.estado = "carregando"
            threading.Thread(target=self._ler, args=(self._processo,), name="voz-motor", daemon=True).start()
            log("[voz] motor da voz natural carregando")
            return True

    def pedir(self, pedido, ao_terminar):
        """Manda um pedido ao trabalhador. Devolve False se ele não estiver rodando."""
        with self._trava:
            if not self.rodando() or self._processo is None:
                return False
            ident = next(self._ids)
            self._pendentes[ident] = ao_terminar
            try:
                self._processo.stdin.write(json.dumps(dict(pedido, id=ident), ensure_ascii=False) + "\n")
                self._processo.stdin.flush()
            except (OSError, ValueError):
                self._pendentes.pop(ident, None)
                return False
            return True

    def desligar(self, espera=3.0):
        """Fecha o trabalhador (libera a memória do modelo). Pedidos pendentes recebem ok=False."""
        with self._trava:
            processo, self._processo = self._processo, None
            self._desligando = True
            self.estado = "desligado"
        if processo is None:
            return
        try:
            processo.stdin.close()                         # fim da entrada: ele sai do laço e termina
        except (OSError, ValueError):
            pass
        try:
            processo.wait(timeout=espera)
        except subprocess.TimeoutExpired:
            processo.terminate()
            try:
                processo.wait(timeout=espera)
            except subprocess.TimeoutExpired:
                processo.kill()

    def _ler(self, processo):
        """Thread: lê as respostas do trabalhador e chama quem pediu."""
        for linha in processo.stdout:
            try:
                resposta = json.loads(linha)
            except ValueError:
                continue
            if resposta.get("evento") == "pronto":
                with self._trava:
                    if self._processo is processo:
                        self.estado = "pronto"
                        self.dispositivo = resposta.get("dispositivo")
                log(f"[voz] voz natural pronta ({resposta.get('dispositivo')}, {resposta.get('segundos')} s)")
                continue
            with self._trava:
                ao_terminar = self._pendentes.pop(resposta.get("id"), None)
            if ao_terminar is not None:
                ao_terminar(resposta)
        with self._trava:                                  # o processo terminou
            pendentes, self._pendentes = self._pendentes, {}
            if self._processo is processo:
                self._processo = None
                self.estado = "desligado" if self._desligando else "falhou"
        if not self._desligando:
            log("[voz] o motor da voz natural fechou sozinho (veja memory/logs/voz_natural.log)")
        for ao_terminar in pendentes.values():
            ao_terminar({"ok": False, "erro": "o motor fechou"})
