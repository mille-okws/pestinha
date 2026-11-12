"""
FRASES COM IA (em teste) - o pet escreve post-its com a IA local: sobre o que sente, ou sobre a tela.

Quem decide é a rede neural: a emoção, o cansaço, a carência e o protesto vêm dela, e são os motores
INVENTAR (frase nova ou já escrita?) e ESPIAR (olhar a tela agora?) que escolhem quando usar a IA.
Aqui isso vira um pedido para o modelo de linguagem (mind/ia_local.py), que só põe em palavras.

O pedido leva só: a personalidade do pet (campo `personalidade` do pets/<pet>.json), o estado dele,
a categoria do que você está fazendo (programando, jogando...; nunca o nome nem o título da janela),
a parte do dia e algumas frases dele como exemplo de estilo. Para comentar a tela, leva também um
print, que é apagado assim que o modelo olha.

As funções daqui rodam na fila do mind/preparo.py (fora da tela): cada tentativa abre o llama.cpp, que
carrega o modelo, escreve e fecha. Uma resposta que não serve (vazia, curta ou comprida demais, com
link, cópia de um exemplo) é descartada, e ele tenta de novo com outra semente, até TENTATIVAS vezes.
"""

import random
import re
import unicodedata
from pathlib import Path

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


def montar_visao(nome, personalidade, estado):
    """(sistema, pedido) para comentar o print da tela."""
    sistema = (
        f"Você é {nome}, um bichinho virtual que vive na tela do computador de uma pessoa. "
        f"{personalidade or PERSONALIDADE_PADRAO}\n"
        "Você acabou de espiar a tela da pessoa. Escreva UM post-it para ela, em português do Brasil, em "
        "primeira pessoa, comentando de um jeito engraçado o que ela está fazendo. No máximo "
        f"{MAX_PALAVRAS - 4} palavras, uma frase só. Sem aspas, sem emoji, sem markdown. Não copie textos, "
        "nomes, números, e-mails nem senhas que aparecem na tela. Escreva só o post-it."
    )
    return sistema, descrever(estado) + "\nEspie a tela acima e escreva o post-it."


def montar_meme(nome, personalidade, estado):
    """(sistema, pedido) para comentar o meme (ou foto) que ele mesmo trouxe: é o que ele fala ao entregar."""
    sistema = (
        f"Você é {nome}, um bichinho virtual que vive na tela do computador de uma pessoa. "
        f"{personalidade or PERSONALIDADE_PADRAO}\n"
        "Você acabou de trazer esta imagem (um meme ou uma foto) para mostrar à pessoa. Escreva o que você fala "
        "ao entregar, em português do Brasil, em primeira pessoa, de um jeito engraçado. No máximo "
        f"{MAX_PALAVRAS - 4} palavras, uma frase só. Sem aspas, sem emoji, sem markdown. Pode reagir ao que está "
        "escrito na imagem, mas não copie o texto dela. Escreva só a fala."
    )
    return sistema, descrever(estado) + "\nOlhe a imagem acima e escreva o que você fala ao entregar."


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


def sem_emoji(texto):
    """Tira emojis (o pedido diz "sem emoji", mas o modelo às vezes põe): símbolos, seletores e tons de pele."""
    texto = unicodedata.normalize("NFC", texto)
    texto = "".join(c for c in texto
                    if unicodedata.category(c) not in ("So", "Cs", "Co", "Cf")
                    and not 0xFE00 <= ord(c) <= 0xFE0F and not 0x1F3FB <= ord(c) <= 0x1F3FF)
    return re.sub(r"\s+", " ", texto).strip()


def limpar(texto, evitar=()):
    """A frase do post-it, ou None se a resposta não serve: vazia, curta ou comprida demais, com link,
    ou igual a uma das frases de `evitar` (os exemplos: copiar não vale)."""
    linhas = [linha.strip() for linha in str(texto or "").splitlines() if linha.strip()]
    if not linhas:
        return None
    frase = re.sub(r"^(post-it|bilhete)\s*:\s*", "", linhas[0], flags=re.I)   # "Post-it: ..."
    frase = sem_emoji(frase.lstrip("-•* ")).strip('"“”\'«»`').strip()
    if len(frase.split()) > MAX_PALAVRAS or len(frase) > MAX_CARACTERES:
        primeira = FIM_DE_FRASE.split(frase)[0]       # comprida: fica a primeira frase, se ela couber
        frase = primeira if primeira != frase else ""
    if not frase or not MIN_PALAVRAS <= len(frase.split()) <= MAX_PALAVRAS or len(frase) > MAX_CARACTERES:
        return None
    if LINK.search(frase) or not any(c.isalpha() for c in frase) or frase.endswith(":"):
        return None
    if _normal(frase) in {_normal(e) for e in evitar}:
        return None
    return frase


# ---------------- escrever (na fila do preparo) ----------------

def _tentar(gerar_uma, evitar, tentativas):
    """Pede até `tentativas` respostas (cada uma com outra semente). Devolve (frase, None) ou (None, motivo)."""
    for _ in range(tentativas):
        try:
            bruto = gerar_uma(random.randrange(2 ** 31))
        except RuntimeError as erro:
            return None, str(erro)                          # o llama.cpp quebrou: tentar de novo não ajuda
        frase = limpar(bruto, evitar)
        if frase:
            return frase, None
    return None, f"nenhuma das {tentativas} respostas serviu"


def escrever(pasta, sistema, pedido, evitar=(), rodar=None, gerar_=ia_local.gerar, tentativas=TENTATIVAS):
    """Escreve um post-it com a IA local. Devolve (frase, None) ou (None, motivo)."""
    prompt = ia_local.chatml(sistema, pedido)
    return _tentar(lambda seed: gerar_(pasta, prompt, rodar=rodar, tokens=TOKENS, seed=seed),
                   tuple(evitar), tentativas)


def comentar(pasta, sistema, pedido, imagem, rodar=None, ver_=ia_local.ver, tentativas=TENTATIVAS):
    """Olha o print e escreve um comentário. Apaga o print no fim, dê certo ou não."""
    try:
        return _tentar(lambda seed: ver_(pasta, sistema, pedido, imagem, rodar=rodar, tokens=TOKENS, seed=seed),
                       tuple(pedido.splitlines()), tentativas)     # repetir o pedido não vale
    finally:
        try:
            Path(imagem).unlink(missing_ok=True)
        except OSError:
            pass
