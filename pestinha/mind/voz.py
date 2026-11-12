"""
VOZ - o pet lê em voz alta os post-its e os cartazes, com a emoção que ele sente na hora.

Dois jeitos de falar, nesta ordem:
    voz natural   OmniVoice, rodando no computador (instalada pelo menu Voz natural, em voz_natural/).
                  A voz de cada pet vem do áudio pets/<pet>/voz/referencia.wav: o modelo imita esse
                  áudio em todas as frases. A emoção entra como marca no texto (risada, suspiro...)
                  e como velocidade. Cada fala gerada fica em cache (memory/voz/<pet>/): na segunda
                  vez, toca na hora.
    sistema       a voz do próprio sistema (`say` no macOS): quando a voz natural não está instalada,
                  o pet não tem referência ou o motor falhou.

Nada trava o pet: o motor gera em outro processo, e só a fala mais recente toca (uma frase nova
interrompe a anterior). Uma fala que fica pronta tarde demais não toca (mas fica no cache).
"""

import hashlib
import re
import threading
import time
import unicodedata
from pathlib import Path

from .. import plataforma

ATRASO_MAXIMO_S = 15.0      # s: a fala ficou pronta depois disso (modelo carregando, fila): não toca
SEED_PADRAO = 11

# emoção do pet -> (marca no começo do texto, fator de velocidade). Marcas que o OmniVoice entende:
# [laughter] risada, [sigh] suspiro, [dissatisfaction-hnn] resmungo, [surprise-ah]/[surprise-oh] susto,
# [question-oh] "oh?". Emoção desconhecida fala normal.
EMOCOES = {
    "feliz":      ("[laughter] ", 1.10),
    "contente":   ("", 1.00),
    "observando": ("", 0.95),
    "curioso":    ("[question-oh] ", 1.00),
    "bravo":      ("[dissatisfaction-hnn] ", 1.15),
    "triste":     ("[sigh] ", 0.85),
    "assustado":  ("[surprise-ah] ", 1.25),
    "dramatico":  ("[sigh] ", 0.75),
    "dormindo":   ("", 0.85),
}


def para_fala(texto):
    """Prepara o texto para ser lido: sem emoji e símbolos, e caixa alta vira minúscula (senão soletra)."""
    limpo = "".join(c for c in str(texto or "")
                    if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co", "Mn", "Cf"))
    limpo = re.sub(r"\s+", " ", unicodedata.normalize("NFC", limpo)).strip()
    letras = [c for c in limpo if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) > 0.6 * len(letras):
        limpo = limpo.lower()
    return limpo if any(c.isalnum() for c in limpo) else ""


def com_emocao(texto, emocao, velocidade_base=1.0):
    """(texto com a marca da emoção, velocidade) para o motor."""
    marca, fator = EMOCOES.get(emocao, ("", 1.0))
    return marca + texto, round(velocidade_base * fator, 3)


class Voz:
    """Fala uma frase por vez: voz natural (com cache) quando dá, senão a voz do sistema."""

    def __init__(self, pasta_cache, motor=None, referencia=None, referencia_texto=None, ajustes=None,
                 sistema=plataforma, relogio=time.monotonic):
        """`ajustes` vem do pets/<pet>.json: {"sistema": "Eddy", "velocidade": 1.15, "seed": 11}."""
        ajustes = ajustes or {}
        self.pasta = Path(pasta_cache)
        self.motor = motor
        self.referencia = Path(referencia) if referencia else None
        self.referencia_texto = Path(referencia_texto) if referencia_texto else None
        self.voz_sistema = ajustes.get("sistema")
        self.velocidade = float(ajustes.get("velocidade", 1.0))
        self.seed = int(ajustes.get("seed", SEED_PADRAO))
        self.sistema = sistema                  # plataforma (trocável nos testes)
        self.relogio = relogio
        self._trava = threading.Lock()
        self._processo = None
        self._atual = None                      # a última frase pedida (gerando ou tocando)
        self._vez = 0                           # cada fala nova (ou parar) invalida as anteriores
        self._marca_da_voz = None
        self.ultimo_motor = None                # "natural", "cache" ou "sistema" (para o log e os testes)

    # ---------------- voz natural ----------------

    def tem_referencia(self):
        """O pet tem voz/referencia.wav e voz/referencia.txt."""
        return bool(self.referencia and self.referencia.exists()
                    and self.referencia_texto and self.referencia_texto.exists())

    def natural(self):
        """Dá para usar a voz natural: instalada e com a referência do pet."""
        return self.motor is not None and self.motor.instalado() and self.tem_referencia()

    def ligar(self):
        """Abre o motor da voz natural (o modelo carrega em segundo plano). Sem ela, não faz nada."""
        if self.natural():
            self.motor.ligar()

    def desligar(self):
        """Cala e fecha o motor (libera a memória do modelo)."""
        self.parar()
        if self.motor is not None:
            self.motor.desligar()

    def _marca(self):
        """Muda quando o áudio ou o texto da referência mudam: aí o cache antigo não vale mais."""
        if self._marca_da_voz is None:
            h = hashlib.sha1(self.referencia.read_bytes())
            h.update(self.referencia_texto.read_bytes())
            self._marca_da_voz = h.hexdigest()[:12]
        return self._marca_da_voz

    def arquivo(self, falado, velocidade):
        """Onde fica (ou vai ficar) a fala gerada desta frase, nesta emoção, com esta voz."""
        chave = f"{self._marca()}\n{falado}\n{velocidade}\n{self.seed}"
        return self.pasta / f"{hashlib.sha1(chave.encode('utf-8')).hexdigest()[:20]}.wav"

    # ---------------- falar ----------------

    def dizer(self, texto, emocao=None):
        """Fala a frase com a emoção (interrompe a anterior). Nunca espera o motor."""
        texto = para_fala(texto)
        if not texto or not self.sistema.TEM_VOZ:
            return
        with self._trava:
            self._vez += 1
            vez = self._vez
            self._parar_processo()
            self._atual = texto
        if self.natural():
            falado, velocidade = com_emocao(texto, emocao, self.velocidade)
            try:
                cache = self.arquivo(falado, velocidade)
            except OSError:
                cache = None
            if cache is not None and cache.exists():
                self._tocar(vez, "cache", texto, self.sistema.tocar_audio, cache)
                return
            if cache is not None and self.motor.rodando():
                pedido = {"texto": falado, "velocidade": velocidade, "seed": self.seed,
                          "referencia": str(self.referencia),
                          "referencia_texto": self.referencia_texto.read_text(encoding="utf-8").strip(),
                          "saida": str(cache)}
                inicio = self.relogio()
                if self.motor.pedir(pedido, lambda r: self._chegou(vez, texto, cache, inicio, r)):
                    return
        self._tocar(vez, "sistema", texto, self.sistema.falar, texto, self.voz_sistema)

    def _chegou(self, vez, texto, cache, inicio, resposta):
        """O motor respondeu (na thread dele): toca, se ainda é a hora; se falhou, usa a voz do sistema."""
        if self.relogio() - inicio > ATRASO_MAXIMO_S:
            return                                          # passou da hora (fica no cache para a próxima)
        if resposta.get("ok") and cache.exists():
            self._tocar(vez, "natural", texto, self.sistema.tocar_audio, cache)
        else:
            self._tocar(vez, "sistema", texto, self.sistema.falar, texto, self.voz_sistema)

    def _tocar(self, vez, motor, texto, comecar, *args):
        """Começa a tocar, se esta ainda é a fala mais recente."""
        with self._trava:
            if vez != self._vez:
                return                                      # outra frase (ou parar) chegou no meio
            self._parar_processo()
            self._processo = comecar(*args)
            self.ultimo_motor = motor

    def parar(self, texto=None):
        """Cala a boca. Com `texto`, só se for essa a frase atual (fecharam o post-it dela): se ela
        ainda estiver sendo gerada, não toca quando ficar pronta."""
        with self._trava:
            if texto is not None and para_fala(texto) != self._atual:
                return
            self._vez += 1
            self._atual = None
            self._parar_processo()

    def _parar_processo(self):
        """Encerra o processo de fala atual (chamar com a trava)."""
        processo, self._processo = self._processo, None
        if processo is not None and processo.poll() is None:
            try:
                processo.terminate()
            except OSError:
                pass
