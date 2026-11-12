"""
ESPIAR CONTROLLER - quando o pet espia a tela para comentar o que você está fazendo (IA local com visão).

Quem decide é o neurônio ESPIAR: quanto mais ele dispara (curioso, com coisa nova na tela), mais
espiadas por segundo, como o TRAVESSURA faz com as travessuras. Cansado, triste ou de castigo, ele
quase não dispara. Entre uma espiada e outra há um intervalo mínimo (ESPIAR_INTERVALO_S).

As regras (permissão "Espiar a tela", IA com visão instalada, permissão do sistema, tela cheia,
dormindo...) ficam no app: aqui só a vontade e o intervalo.
"""

import random

from ..ajustes import ESPIAR_INTERVALO_S, GANHO_ESPIAR

INTERVALO_TESTE_S = 30.0    # no modo teste: espia de novo depois de 30 s
GANHO_TESTE = 20.0          # no modo teste: 20 vezes mais vontade


class EspiarController:
    """A vontade de espiar (taxa do ESPIAR) e o intervalo mínimo entre espiadas."""

    def __init__(self, debug):
        self.debug = debug
        self.ultima = None          # quando espiou pela última vez (monotonic)

    def intervalo(self):
        """Tempo mínimo entre espiadas."""
        return INTERVALO_TESTE_S if self.debug() else ESPIAR_INTERVALO_S

    def descansando(self, now):
        """Ainda não passou o intervalo desde a última espiada."""
        return self.ultima is not None and now - self.ultima < self.intervalo()

    def quer(self, now, dt, taxa):
        """O neurônio ESPIAR disparou o bastante neste quadro (e já passou o intervalo)."""
        if self.descansando(now):
            return False
        ganho = GANHO_ESPIAR * (GANHO_TESTE if self.debug() else 1.0)
        return random.random() < taxa * ganho * dt

    def espiou(self, now):
        """Marca a espiada (conta mesmo se der errado: não fica tentando sem parar)."""
        self.ultima = now
