"""
VOZ - o pet lê em voz alta os post-its e os cartazes, com a emoção que ele sente na hora.

Dois jeitos de falar:
    voz natural   OmniVoice, rodando no computador (instalada pelo menu Voz natural, em voz_natural/).
                  A voz de cada pet vem do áudio pets/<pet>/voz/referencia.wav: o modelo imita esse
                  áudio em todas as frases. A emoção entra como marca no texto (risada, suspiro...)
                  e como velocidade.
    sistema       a voz do próprio sistema (`say` no macOS): quando a voz natural não está instalada,
                  o pet não tem referência ou a geração falhou.

A fala natural é gerada ANTES de o post-it aparecer, na fila do mind/preparo.py: o modelo carrega,
gera o áudio e é descarregado. Só então o post-it aparece, junto com o áudio, e o arquivo é apagado
assim que termina de tocar (ou quando alguém fecha o post-it). Nada fica guardado.

    preparar(texto, emocao, rodar)   (thread do preparo) gera o áudio num arquivo temporário
    anexar(texto, arquivo)           (tela) guarda o áudio pronto daquela frase
    dizer(texto, emocao)             (tela) a frase apareceu: toca o áudio dela, ou a voz do sistema
    recolher()                       (tela, a cada quadro) apaga o áudio que terminou de tocar
"""


import re
import time
import unicodedata
import uuid
from pathlib import Path

from .. import plataforma

ESQUECIDO_S = 300.0         # s: áudio pronto que nenhum post-it usou (desligaram no meio): apagado
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
    # cartazes da greve e da revolução (não são emoções do rosto): palavra de ordem, sem pressa
    "grevista":   ("[dissatisfaction-hnn] ", 0.90),
    "revoltado":  ("[dissatisfaction-hnn] ", 0.90),
}

# Quanto a fala sobe. O OmniVoice não tem "gritar" na clonagem: o que dá é exclamar (a entonação sobe),
# aumentar o volume (o pico do áudio; o normal é VOLUME_PADRAO) e repetir a palavra de ordem: ele fala,
# espera REPETIR_APOS_S e fala de novo (REPETICOES vezes), como numa passeata.
VOLUME_PADRAO = 0.5
INTENSIDADE = {
    "bravo":     {"exclamar": True},
    "grevista":  {"exclamar": True, "volume": 0.7, "repetir": True},
    "revoltado": {"exclamar": True, "volume": 0.9, "repetir": True},
}
REPETIR_APOS_S = 0.5            # s de silêncio entre uma vez e a outra
REPETICOES = 1                  # quantas vezes ele repete depois da primeira


def para_fala(texto):
    """Prepara o texto para ser lido: sem emoji e símbolos, e caixa alta vira minúscula (senão soletra)."""
    limpo = "".join(c for c in str(texto or "")
                    if unicodedata.category(c) not in ("So", "Sk", "Cs", "Co", "Mn", "Cf"))
    limpo = re.sub(r"\s+", " ", unicodedata.normalize("NFC", limpo)).strip()
    letras = [c for c in limpo if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) > 0.6 * len(letras):
        limpo = limpo.lower()
    return limpo if any(c.isalnum() for c in limpo) else ""


def exclamar(texto):
    """Termina em "!" (a entonação sobe); pergunta continua pergunta."""
    texto = texto.rstrip(" .…;,")
    return texto if texto.endswith(("!", "?")) else texto + "!"


def com_emocao(texto, emocao, velocidade_base=1.0):
    """(texto com a marca da emoção, velocidade) para o motor. Bravo, greve e revolução exclamam."""
    marca, fator = EMOCOES.get(emocao, ("", 1.0))
    if INTENSIDADE.get(emocao, {}).get("exclamar"):
        texto = exclamar(texto)
    return marca + texto, round(velocidade_base * fator, 3)


def repete(emocao):
    """Esta emoção é palavra de ordem: depois de falar, ele espera e fala de novo."""
    return bool(INTENSIDADE.get(emocao, {}).get("repetir"))


def volume_da_emocao(emocao):
    """Pico do áudio final para esta emoção (a revolução sai mais alta)."""
    return INTENSIDADE.get(emocao, {}).get("volume", VOLUME_PADRAO)


def _apagar(caminho):
    """Apaga o arquivo (e o .tmp que o trabalhador deixa enquanto escreve), sem reclamar se já sumiu."""
    if caminho is None:
        return
    for arquivo in (Path(caminho), Path(str(caminho) + ".tmp")):
        try:
            arquivo.unlink(missing_ok=True)
        except OSError:
            pass


class Voz:
    """Fala uma frase por vez: o áudio natural preparado antes, ou a voz do sistema na hora."""

    def __init__(self, pasta, motor=None, referencia=None, referencia_texto=None, ajustes=None,
                 sistema=plataforma, relogio=time.monotonic):
        """`pasta` recebe os áudios enquanto existem; `ajustes` vem do pets/<pet>.json."""
        ajustes = ajustes or {}
        self.pasta = Path(pasta)
        self.motor = motor
        self.referencia = Path(referencia) if referencia else None
        self.referencia_texto = Path(referencia_texto) if referencia_texto else None
        self.voz_sistema = ajustes.get("sistema")
        self.velocidade = float(ajustes.get("velocidade", 1.0))
        self.seed = int(ajustes.get("seed", SEED_PADRAO))
        self.sistema = sistema                  # plataforma (trocável nos testes)
        self.relogio = relogio
        self._anexados = {}                     # frase falada -> (arquivo, quando ficou pronto)
        self._processo = None                   # o que está tocando
        self._arquivo = None                    # o áudio que está tocando (apagado quando termina)
        self._atual = None                      # a frase que está tocando (ou esperando para repetir)
        self._repetir = None                    # palavra de ordem: {"faltam": n, "quando": hora da próxima}
        # () -> (vezes, pausa em s) da palavra de ordem; o app liga nas Configurações (Voz)
        self.repeticao = lambda: (REPETICOES, REPETIR_APOS_S)
        self.ultimo_motor = None                # "natural" ou "sistema" (para o log e os testes)

    # ---------------- voz natural ----------------

    def tem_referencia(self):
        """O pet tem voz/referencia.wav e voz/referencia.txt."""
        return bool(self.referencia and self.referencia.exists()
                    and self.referencia_texto and self.referencia_texto.exists())

    def natural(self):
        """Dá para usar a voz natural: instalada e com a referência do pet."""
        return self.motor is not None and self.motor.instalado() and self.tem_referencia()

    def preparar(self, texto, emocao=None, rodar=None):
        """
        (Thread do preparo) Gera a fala natural desta frase num arquivo: o motor carrega o modelo,
        gera e fecha. Devolve o arquivo, ou None se não deu (aí o pet usa a voz do sistema).
        """
        falado = para_fala(texto)
        if not falado or not self.natural():
            return None
        fala, velocidade = com_emocao(falado, emocao, self.velocidade)
        saida = self.pasta / f"fala-{uuid.uuid4().hex[:12]}.wav"
        pedido = {"texto": fala, "velocidade": velocidade, "seed": self.seed,
                  "volume": volume_da_emocao(emocao),
                  "referencia": str(self.referencia),
                  "referencia_texto": self.referencia_texto.read_text(encoding="utf-8").strip(),
                  "saida": str(saida)}
        try:
            self.pasta.mkdir(parents=True, exist_ok=True)
            resposta = self.motor.gerar(pedido, rodar=rodar)
        except BaseException:
            _apagar(saida)                      # cancelada no meio: nada de áudio pela metade
            raise
        if resposta.get("ok") and saida.exists():
            return saida
        _apagar(saida)
        return None

    def anexar(self, texto, arquivo):
        """(Tela) O áudio desta frase ficou pronto: toca quando ela aparecer."""
        chave = para_fala(texto)
        antigo = self._anexados.pop(chave, None)
        if antigo is not None and antigo[0] != Path(arquivo):
            _apagar(antigo[0])
        if not chave:
            _apagar(arquivo)
            return
        self._anexados[chave] = (Path(arquivo), self.relogio())

    def descartar(self, texto):
        """O post-it desta frase não vai aparecer (ou apareceu sem falar): apaga o áudio dele."""
        item = self._anexados.pop(para_fala(texto), None)
        if item is not None:
            _apagar(item[0])

    # ---------------- falar ----------------

    def dizer(self, texto, emocao=None):
        """A frase apareceu: toca o áudio preparado dela (interrompe a anterior) ou usa a voz do sistema."""
        texto = para_fala(texto)
        if not texto:
            return
        anexado = self._anexados.pop(texto, None)
        if not self.sistema.TEM_VOZ:
            if anexado is not None:
                _apagar(anexado[0])
            return
        self._parar_processo()
        if anexado is not None and anexado[0].exists():
            self._processo = self.sistema.tocar_audio(anexado[0])
            self._arquivo, self._atual, self.ultimo_motor = anexado[0], texto, "natural"
            if self._processo is None:              # não abriu o player: apaga e cai na voz do sistema
                _apagar(anexado[0])
                self._arquivo = None
            else:
                self._repetir = self._palavra_de_ordem(emocao)
                return
        self._processo = self.sistema.falar(texto, self.voz_sistema)
        self._atual, self.ultimo_motor = texto, "sistema"
        self._repetir = self._palavra_de_ordem(emocao)

    def _palavra_de_ordem(self, emocao):
        """Quantas repetições esta fala ainda tem (greve, revolução), ou None se não repete."""
        vezes = int(self.repeticao()[0]) if repete(emocao) else 0
        return {"faltam": vezes, "quando": None} if vezes > 0 else None

    def recolher(self, pode_repetir=True):
        """
        (Tela, a cada quadro) Apaga o áudio que terminou de tocar e o que ninguém usou. Na palavra de
        ordem (greve, revolução), guarda o áudio, espera REPETIR_APOS_S e toca de novo; `pode_repetir`
        falso (escondido, pausado, voz desligada) desiste da repetição.
        """
        agora = self.relogio()
        if self._processo is not None and self._processo.poll() is not None:
            self._processo = None
            rep = self._repetir
            if rep is not None and rep["faltam"] > 0 and pode_repetir:
                rep["quando"] = agora + float(self.repeticao()[1])   # o áudio fica: vai tocar de novo
            else:
                self._esquecer_atual()
        rep = self._repetir
        if self._processo is None and rep is not None and rep["quando"] is not None:
            if not pode_repetir:
                self._esquecer_atual()
            elif agora >= rep["quando"]:
                rep["faltam"] -= 1
                rep["quando"] = None
                if self._arquivo is not None and self._arquivo.exists():
                    self._processo = self.sistema.tocar_audio(self._arquivo)
                else:
                    self._processo = self.sistema.falar(self._atual, self.voz_sistema)
                if self._processo is None:
                    self._esquecer_atual()
        for chave, (arquivo, quando) in list(self._anexados.items()):
            if agora - quando > ESQUECIDO_S:
                del self._anexados[chave]
                _apagar(arquivo)

    def parar(self, texto=None):
        """Cala a boca. Com `texto`, só se for essa a frase que está tocando (fecharam o post-it dela)."""
        if texto is not None and para_fala(texto) != self._atual:
            return
        self._parar_processo()

    def desligar(self):
        """Cala e apaga todos os áudios (fechar, pânico, voz desligada)."""
        self._parar_processo()
        for arquivo, _quando in self._anexados.values():
            _apagar(arquivo)
        self._anexados.clear()

    def limpar_pasta(self):
        """Ao abrir: apaga áudios que sobraram de uma vez em que o programa fechou no meio."""
        if not self.pasta.is_dir():
            return
        for arquivo in list(self.pasta.glob("*.wav")) + list(self.pasta.glob("*.wav.tmp")):
            _apagar(arquivo)

    def _parar_processo(self):
        """Encerra o que está tocando e apaga o áudio dele."""
        processo, self._processo = self._processo, None
        if processo is not None and processo.poll() is None:
            try:
                processo.terminate()
            except OSError:
                pass
        self._esquecer_atual()

    def _esquecer_atual(self):
        """A frase acabou de vez: apaga o áudio dela e desiste de repetir."""
        _apagar(self._arquivo)
        self._arquivo, self._atual, self._repetir = None, None, None
