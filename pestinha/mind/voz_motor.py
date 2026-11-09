"""
MOTOR DA VOZ NATURAL - abre o trabalhador do OmniVoice (mind/omnivoice_trabalhador.py) para gerar UMA fala.

O trabalhador roda com o Python de voz_natural/ambiente (onde estão o torch e o OmniVoice), num
processo separado: o Pestinha não depende do torch e continua leve para quem não instalou a voz.

Cada fala é um processo: ele abre, carrega o modelo, gera o áudio, responde e fecha. Assim o modelo
(uns 3 GB) só ocupa memória enquanto a fala está sendo gerada, e nunca junto com a IA local
(mind/preparo.py roda uma coisa por vez). A conversa é por linhas de JSON na entrada e na saída
padrão (nenhuma porta de rede é aberta):

    entrada   {"id": 1, "texto": ..., "velocidade": ..., "seed": ..., "referencia": ..., "saida": ...}
    saída     {"evento": "pronto", "dispositivo": "mps", "segundos": 2.1}   (depois de carregar)
              {"id": 1, "ok": true, ...}  ou  {"id": 1, "ok": false, "erro": "..."}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from ..log import log

TRABALHADOR = Path(__file__).with_name("omnivoice_trabalhador.py")
TEMPO_MAXIMO_S = 180.0      # s: carregar (a 1ª vez compila para a GPU) + gerar, com novas tentativas


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


def _rodar_simples(cmd, entrada=None, tempo=TEMPO_MAXIMO_S, erros=subprocess.PIPE, ambiente=None):
    """Sem o preparo (linha de comando, testes): roda e espera."""
    try:
        return subprocess.run(cmd, input=entrada, stdout=subprocess.PIPE, stderr=erros, timeout=tempo,
                              env=ambiente, check=False)
    except subprocess.TimeoutExpired as erro:
        raise RuntimeError(f"passou de {tempo:.0f} s") from erro


class MotorVoz:
    """Gera falas com o OmniVoice, uma por processo."""

    def __init__(self, pasta, log_arquivo=None, python=None, trabalhador=TRABALHADOR):
        """`pasta` é voz_natural/; `log_arquivo` recebe o que o trabalhador escreve no stderr."""
        self.pasta = Path(pasta)
        self.log_arquivo = Path(log_arquivo) if log_arquivo else None
        self.python = Path(python) if python else None        # só os testes trocam
        self.trabalhador = Path(trabalhador)
        self.dispositivo = None                               # "mps", "cuda:0" ou "cpu" (da última fala)
        self.carregou_s = None                                # quanto o modelo levou para carregar

    def instalado(self):
        """Diz se dá para gerar (os testes, com `python` próprio, não precisam da instalação)."""
        return self.python is not None or instalada(self.pasta)

    def gerar(self, pedido, rodar=None, tempo=TEMPO_MAXIMO_S):
        """
        Abre o trabalhador, que carrega o modelo, gera esta fala em pedido["saida"] e fecha.
        Devolve a resposta dele ({"ok": True, ...} ou {"ok": False, "erro": ...}). Nunca levanta,
        a não ser a Cancelada do preparo (`rodar` é o Controle.rodar dele).
        """
        if not self.instalado():
            return {"ok": False, "erro": "a voz natural não está instalada"}
        python = self.python or python_do_ambiente(self.pasta)
        cmd = [str(python), "-u", str(self.trabalhador), "--modelo", str(self.pasta / "modelo")]
        entrada = (json.dumps(dict(pedido, id=1), ensure_ascii=False) + "\n").encode("utf-8")
        ambiente = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        erros = subprocess.DEVNULL
        if self.log_arquivo is not None:
            try:
                self.log_arquivo.parent.mkdir(parents=True, exist_ok=True)
                erros = open(self.log_arquivo, "ab")
            except OSError:
                erros = subprocess.DEVNULL
        try:
            r = (rodar or _rodar_simples)(cmd, entrada=entrada, tempo=tempo, erros=erros, ambiente=ambiente)
        except (OSError, RuntimeError) as erro:
            log(f"[voz] o motor da voz natural não gerou: {erro}")
            return {"ok": False, "erro": str(erro)}
        finally:
            if erros is not subprocess.DEVNULL:
                erros.close()
        resposta = None
        for linha in (r.stdout or b"").decode("utf-8", errors="replace").splitlines():
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("evento") == "pronto":
                self.dispositivo, self.carregou_s = msg.get("dispositivo"), msg.get("segundos")
            elif msg.get("id") == 1:
                resposta = msg
        if resposta is None:
            erro = f"o motor saiu com o código {r.returncode} sem responder (veja memory/logs/voz_natural.log)"
            log(f"[voz] {erro}")
            return {"ok": False, "erro": erro}
        return resposta
