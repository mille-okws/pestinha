"""
FRASES COM IA (em teste) - o pet escreve um post-it sobre o que sente agora, com a IA local.

Quem sente é a rede neural: emoção, energia, carência e protesto vêm dela. Aqui isso vira um pedido
para o modelo de linguagem (mind/ia_local.py), que só põe em palavras. O modelo nunca decide nada.

O pedido leva só: a personalidade do pet (campo `personalidade` do pets/<pet>.json), o estado dele,
a categoria do que você está fazendo (programando, jogando...; nunca o nome nem o título da janela),
a parte do dia e algumas frases dele como exemplo de estilo.

Cada pedido abre o llama.cpp num QProcess (a tela não trava), que carrega o modelo, escreve e fecha.
Uma resposta que não serve (vazia, curta ou comprida demais, com link, cópia de um exemplo) é
descartada, e ele tenta de novo com outra semente, até TENTATIVAS vezes.
"""

import random
import re
import time
import unicodedata

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from . import ia_local

TENTATIVAS = 3
MIN_PALAVRAS = 3                # "PROGRAMANDO." não diz nada
MAX_PALAVRAS = 14
MAX_CARACTERES = 90
EXEMPLOS = 5                    # frases do pet mostradas como estilo
TOKENS = 40

PERSONALIDADE_PADRAO = "Você é um bichinho virtual curioso e brincalhão."

# emoção da rede -> como ela entra no pedido
EMOCOES = {
    "feliz": "feliz e animado",
    "contente": "tranquilo e contente",
    "observando": "quieto, observando a pessoa",
    "curioso": "curioso com o que a pessoa está fazendo",
    "bravo": "bravo e irritado com a pessoa",
    "triste": "triste, se sentindo ignorado",
    "assustado": "assustado",
    "dramatico": "fazendo drama, se sentindo injustiçado",
    "dormindo": "com muito sono, quase dormindo",
}
# categoria do programa em primeiro plano (sense/senses.py) -> o que a pessoa está fazendo
ATIVIDADES = {
    "PROGRAMMING": "A pessoa está programando.",
    "DESIGNING": "A pessoa está desenhando ou editando no computador.",
    "GAMING": "A pessoa está jogando.",
    "BROWSING": "A pessoa está navegando na internet.",
    "MUSIC": "A pessoa está ouvindo música.",
    "SOCIAL": "A pessoa está conversando com alguém no computador.",
    "AWAY": "A pessoa saiu de perto do computador.",
}
PROTESTO = {1: "reclamando da pessoa", 2: "fazendo manifestação contra a pessoa",
            3: "em greve", 4: "em revolução contra o cursor"}

LINK = re.compile(r"https?://|www\.|\.com\b|\.br\b|@\w", re.I)
FIM_DE_FRASE = re.compile(r"(?<=[.!?…])\s")


# ---------------- pedido ----------------

def parte_do_dia(hora):
    """0-23 -> 'de madrugada', 'de manhã', 'à tarde' ou 'à noite'."""
    if hora < 6:
        return "de madrugada"
    if hora < 12:
        return "de manhã"
    if hora < 18:
        return "à tarde"
    return "à noite"


SENTIDO = 0.4                   # intensidade (0-1) a partir da qual o sentido interno entra no pedido


def descrever(estado):
    """
    O que a rede sente, em frases curtas. `estado`: emocao, os sentidos internos que entram na rede
    (cansaco, carencia, tedio: 0-1, de drives.channels()), atividade (categoria), protesto (0-4) e
    hora (0-23). Tudo opcional.
    """
    partes = [f"Agora você está {EMOCOES.get(estado.get('emocao'), 'tranquilo')}."]
    if (estado.get("cansaco") or 0) > SENTIDO:
        partes.append("Você está cansado, sem energia.")
    if (estado.get("carencia") or 0) > SENTIDO:
        partes.append("Você está carente, querendo atenção.")
    if (estado.get("tedio") or 0) > SENTIDO:
        partes.append("Você está entediado.")
    if estado.get("protesto") in PROTESTO:
        partes.append(f"Você está {PROTESTO[estado['protesto']]}.")
    if estado.get("atividade") in ATIVIDADES:
        partes.append(ATIVIDADES[estado["atividade"]])
    if estado.get("hora") is not None:
        partes.append(f"É {parte_do_dia(estado['hora'])}.")
    return " ".join(partes)


def montar(nome, personalidade, estado, exemplos=()):
    """(sistema, pedido) para o modelo."""
    sistema = (
        f"Você é {nome}, um bichinho virtual que vive na tela do computador de uma pessoa. "
        f"{personalidade or PERSONALIDADE_PADRAO}\n"
        "Escreva UM post-it para a pessoa, em português do Brasil, em primeira pessoa, mostrando como "
        f"você está se sentindo agora. No máximo {MAX_PALAVRAS - 4} palavras, uma frase só. Sem aspas, "
        "sem emoji, sem hashtag, sem links. Não cite pessoas, marcas nem empresas reais. "
        "Escreva só o post-it."
    )
    pedido = descrever(estado)
    exemplos = [e for e in exemplos if e][:EXEMPLOS]
    if exemplos:
        pedido += "\nExemplos do seu jeito de escrever (não copie):\n" + "\n".join(f"- {e}" for e in exemplos)
    return sistema, pedido + "\nEscreva o post-it."


# ---------------- resposta ----------------

def _normal(frase):
    """Para comparar frases: minúsculas, sem acentos, pontuação nem espaços sobrando."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", frase.lower()) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", sem_acento).split())


def limpar(texto, evitar=()):
    """A frase do post-it, ou None se a resposta não serve: vazia, curta ou comprida demais, com link,
    ou igual a uma das frases de `evitar` (os exemplos: copiar não vale)."""
    linhas = [linha.strip() for linha in str(texto or "").splitlines() if linha.strip()]
    if not linhas:
        return None
    frase = re.sub(r"^(post-it|bilhete)\s*:\s*", "", linhas[0], flags=re.I)   # "Post-it: ..."
    frase = frase.lstrip("-•* ").strip().strip('"“”\'«»`').strip()
    if len(frase.split()) > MAX_PALAVRAS or len(frase) > MAX_CARACTERES:
        primeira = FIM_DE_FRASE.split(frase)[0]       # comprida: fica a primeira frase, se ela couber
        frase = primeira if primeira != frase else ""
    if not frase or not MIN_PALAVRAS <= len(frase.split()) <= MAX_PALAVRAS or len(frase) > MAX_CARACTERES:
        return None
    if LINK.search(frase) or not any(c.isalpha() for c in frase):
        return None
    if _normal(frase) in {_normal(e) for e in evitar}:
        return None
    return frase


# ---------------- o pedido rodando ----------------

class FrasesIA(QObject):
    """Gera uma frase por vez, em outro processo; avisa por sinal quando fica pronta."""

    pronta = Signal(str, float)       # (frase, segundos desde o pedido)
    falhou = Signal(str)              # motivo

    def __init__(self, pasta, programa=None, parent=None):
        """`pasta` é ia_local/; `programa` (lista de comando) só é trocado nos testes."""
        super().__init__(parent)
        self.pasta = pasta
        self.programa = programa
        self.processo = None
        self._prompt = None
        self._evitar = ()
        self._tentativa = 0
        self._inicio = 0.0
        self._estourou = False
        self._prazo = QTimer(self)
        self._prazo.setSingleShot(True)
        self._prazo.timeout.connect(self._passou_do_prazo)

    def instalada(self):
        """A IA local está instalada (ou os testes trocaram o programa)."""
        return self.programa is not None or ia_local.instalada(self.pasta)

    def ocupada(self):
        """Está escrevendo uma frase agora."""
        return self.processo is not None

    def pedir(self, sistema, pedido, evitar=()):
        """Começa a escrever. `evitar`: frases que não valem (os exemplos). Devolve False se não estiver
        instalada ou já estiver escrevendo."""
        if self.ocupada() or not self.instalada():
            return False
        self._prompt = ia_local.chatml(sistema, pedido)
        self._evitar = tuple(evitar)
        self._tentativa = 0
        self._estourou = False
        self._inicio = time.monotonic()
        self._rodar()
        return True

    def _rodar(self):
        """Uma tentativa: abre o llama.cpp com uma semente nova."""
        self._tentativa += 1
        cmd = ia_local.comando(self.pasta, self._prompt, tokens=TOKENS, seed=random.randrange(2 ** 31),
                               programa_=self.programa)
        self.processo = QProcess(self)
        self.processo.setStandardInputFile(QProcess.nullDevice())
        self.processo.finished.connect(self._terminou)
        self.processo.errorOccurred.connect(self._erro)
        self.processo.start(cmd[0], cmd[1:])
        self._prazo.start(int(ia_local.TEMPO_MAXIMO_S * 1000))

    def _terminou(self, codigo, _status=None):
        """O llama.cpp fechou: confere a frase; se não serve, tenta de novo."""
        processo, self.processo = self.processo, None
        self._prazo.stop()
        if processo is None:
            return
        saida = bytes(processo.readAllStandardOutput())
        erro = bytes(processo.readAllStandardError()).decode("utf-8", errors="replace").strip()
        processo.deleteLater()
        frase = limpar(ia_local.resposta(saida), self._evitar) if codigo == 0 else None
        if frase:
            self.pronta.emit(frase, time.monotonic() - self._inicio)
        elif self._tentativa < TENTATIVAS and not self._estourou:
            self._rodar()
        elif self._estourou:
            self.falhou.emit(f"demorou mais de {ia_local.TEMPO_MAXIMO_S:.0f} s")
        elif codigo != 0:
            ultima = erro.splitlines()[-1] if erro else "?"
            self.falhou.emit(f"o llama.cpp saiu com o código {codigo}: {ultima[:200]}")
        else:
            self.falhou.emit(f"nenhuma das {TENTATIVAS} respostas serviu")

    def _erro(self, erro):
        """Não conseguiu nem abrir o llama.cpp."""
        if erro == QProcess.FailedToStart and self.processo is not None:
            processo, self.processo = self.processo, None
            self._prazo.stop()
            processo.deleteLater()
            self.falhou.emit("não abriu o llama.cpp")

    def _passou_do_prazo(self):
        """Demorou demais: cancela (o finished que vem do kill vira mais uma tentativa ou a falha)."""
        if self.processo is not None:
            self._estourou = True
            self.processo.kill()

    def cancelar(self):
        """Para de escrever (ao fechar o programa ou no pânico)."""
        processo, self.processo = self.processo, None
        self._prazo.stop()
        if processo is not None:
            processo.finished.disconnect()
            processo.kill()
            processo.waitForFinished(2000)
            processo.deleteLater()
