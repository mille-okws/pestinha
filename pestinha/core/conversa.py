"""
CONVERSA - regras puras da conversa em texto com o pet: limites, contexto mínimo, provedores e validação da resposta.

Opcional e desligada por padrão (permissão "conversa"). Não mexe na rede neural, no comportamento
nem na memória do pet: ele só empresta o nome e a emoção do momento para o contexto. Nada daqui grava
em disco.

Um provedor recebe um `Pedido` e devolve texto. Ele roda fora da thread do Qt (ver ui/conversa.py) e
deve olhar o evento `cancelado` para desistir cedo. Para ligar um modelo de verdade, crie uma subclasse
de `Provedor`, diga em `envia_para_fora` se o texto sai do computador e registre em `PROVEDORES`.
Chaves de API vêm de variável de ambiente, nunca do código nem de arquivos do repositório.
"""

import random
import re
from dataclasses import dataclass

from ..ajustes import CONVERSA_MAX_ENTRADA, CONVERSA_MAX_RESPOSTA

# caracteres de controle (menos a quebra de linha), que não devem chegar à tela nem ao modelo
_CONTROLE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


class ErroConversa(Exception):
    """Falha que vira uma mensagem curta na janela (sem mostrar detalhes técnicos)."""
    mensagem = "Algo deu errado. Tente de novo."


class SemConexao(ErroConversa):
    """O provedor precisa de internet e ela não está disponível."""
    mensagem = "Sem conexão com a internet. A conversa continua desligada do modelo."


class ModeloIndisponivel(ErroConversa):
    """O modelo não respondeu (não instalado, fora do ar, sem chave)."""
    mensagem = "O modelo não está disponível agora."


class RespostaInvalida(ErroConversa):
    """O modelo devolveu algo que não é texto ou veio vazio."""
    mensagem = "O modelo respondeu algo que não dá para mostrar."


class Cancelado(ErroConversa):
    """A resposta foi cancelada antes de chegar."""
    mensagem = "Resposta cancelada."


@dataclass(frozen=True)
class Pedido:
    """Tudo o que vai para o modelo: o texto que você digitou, o nome do pet e a emoção dele agora. Nada mais."""
    texto: str
    nome_pet: str
    emocao: str


def limpar_entrada(texto):
    """Confere a mensagem digitada: tira caracteres de controle e espaços das pontas; vazia ou longa demais levanta ValueError."""
    if not isinstance(texto, str):
        raise ValueError("A mensagem precisa ser texto.")
    limpo = _CONTROLE.sub("", texto).strip()
    if not limpo:
        raise ValueError("Escreva alguma coisa antes de enviar.")
    if len(limpo) > CONVERSA_MAX_ENTRADA:
        raise ValueError(f"Mensagem longa demais: no máximo {CONVERSA_MAX_ENTRADA} caracteres.")
    return limpo


def montar_pedido(texto, nome_pet, emocao):
    """Monta o pedido com o contexto mínimo. Levanta ValueError se a mensagem não servir."""
    return Pedido(texto=limpar_entrada(texto), nome_pet=str(nome_pet)[:40], emocao=str(emocao)[:30])


def validar_resposta(resposta):
    """Aceita só texto não vazio; tira caracteres de controle e corta no limite. Senão, RespostaInvalida."""
    if not isinstance(resposta, str):
        raise RespostaInvalida()
    limpo = _CONTROLE.sub("", resposta).strip()
    if not limpo:
        raise RespostaInvalida()
    if len(limpo) > CONVERSA_MAX_RESPOSTA:
        limpo = limpo[: CONVERSA_MAX_RESPOSTA - 1].rstrip() + "…"
    return limpo


class Provedor:
    """Interface de quem responde. `responder` roda fora da thread do Qt e pode demorar."""
    nome = "base"
    descricao = ""
    envia_para_fora = False     # True: o texto sai do computador (a janela avisa)

    def responder(self, pedido, cancelado):
        """Devolve o texto da resposta. `cancelado` é um threading.Event: se ele ligar, desista (levante Cancelado)."""
        raise NotImplementedError


class ProvedorSimulado(Provedor):
    """
    Respostas prontas, para testar a conversa sem modelo nenhum. Nada sai do computador.

    Comandos para testar os erros: /lento (passa do tempo máximo), /erro (modelo indisponível),
    /semrede (sem internet) e /invalido (resposta vazia).
    """
    nome = "simulado"
    descricao = "Modo simulado: respostas prontas, sem modelo de linguagem. Nada sai do computador."
    envia_para_fora = False

    FRASES = {
        "feliz": ["Tô muito feliz! Fala mais!", "Que dia bom, hein?"],
        "contente": ["Tô tranquilo aqui. E você?", "Gostei de conversar."],
        "curioso": ["Hmm, e o que mais?", "Me conta direito isso."],
        "observando": ["Tô de olho em tudo.", "Entendi. Continuo aqui olhando."],
        "bravo": ["Hmpf. Agora não tô muito a fim de papo.", "Tô bravo, mas tô ouvindo."],
        "triste": ["Obrigado por falar comigo.", "Tava meio sozinho. Bom te ouvir."],
        "assustado": ["Ai! Você me assustou.", "Calma, calma..."],
        "dramatico": ["Ninguém me entende!", "Que drama, né? Mas eu ouvi."],
        "dormindo": ["Zzz... (ele está dormindo)"],
    }

    def __init__(self, atraso=(0.4, 1.2), rng=None):
        """`atraso`: segundos (mínimo, máximo) para fingir que está pensando."""
        self.atraso = atraso
        self.rng = rng or random.Random()

    def responder(self, pedido, cancelado):
        """Responde conforme a emoção; os comandos simulam lentidão, erro, falta de rede e resposta inválida."""
        comando = pedido.texto.strip().lower()
        if comando == "/erro":
            raise ModeloIndisponivel()
        if comando == "/semrede":
            raise SemConexao()
        espera = 3600.0 if comando == "/lento" else self.rng.uniform(*self.atraso)
        if cancelado.wait(espera):
            raise Cancelado()
        if comando == "/invalido":
            return "   "
        frases = self.FRASES.get(pedido.emocao, self.FRASES["observando"])
        resposta = self.rng.choice(frases)
        if pedido.texto.rstrip().endswith("?"):
            resposta += " (No modo simulado eu não sei responder perguntas de verdade.)"
        return resposta


PROVEDORES = {"simulado": ProvedorSimulado}


def criar_provedor(nome="simulado"):
    """Cria o provedor pelo nome; um nome desconhecido vira o simulado (nunca liga um modelo por engano)."""
    return PROVEDORES.get(nome, ProvedorSimulado)()
