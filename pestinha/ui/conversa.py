"""
JANELA DE CONVERSA - caixa de texto para conversar com o pet; o provedor roda numa thread separada e a interface não espera.

Uma resposta por vez. O tempo máximo, o cancelamento e o fechamento da janela descartam a resposta que
ainda não chegou (uma resposta atrasada é ignorada pelo número do pedido). A conversa fica só nesta
janela, na memória: nada é gravado em disco e tudo some ao fechar.
"""

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ajustes import CONVERSA_MAX_ENTRADA, CONVERSA_MAX_LINHAS, CONVERSA_TEMPO_MAX
from ..core.conversa import ErroConversa, montar_pedido, validar_resposta
from ..log import log
from .ui import STYLE, face_icon


class _Ponte(QObject):
    """Leva o resultado da thread do provedor de volta para a thread do Qt."""
    terminou = Signal(int, object, object)      # número do pedido, resposta (str ou None), erro (ou None)


class JanelaConversa(QWidget):
    """Janela de conversa. `emocao_atual` é uma função que devolve a emoção do pet agora (só leitura)."""

    fechada = Signal()

    def __init__(self, provedor, nome_pet, emocao_atual, tempo_max=CONVERSA_TEMPO_MAX):
        """Monta a janela e o aviso de privacidade conforme o provedor (se o texto sai ou não do computador)."""
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.provedor = provedor
        self.nome_pet = nome_pet
        self.emocao_atual = emocao_atual
        self.tempo_max = tempo_max
        self._numero = 0
        self._pendente = None           # (número, evento de cancelamento) da resposta em andamento
        self._ponte = _Ponte(self)
        self._ponte.terminou.connect(self._terminou)
        self._relogio = QTimer(self)
        self._relogio.setSingleShot(True)
        self._relogio.timeout.connect(self._estourou)

        self.setWindowTitle(f"Conversar com {nome_pet}")
        self.setWindowIcon(face_icon())
        self.setStyleSheet(STYLE + "QWidget { background: #0c1f13; } "
                           "QPlainTextEdit, QLineEdit { background: #17201a; color: #dfffe6; "
                           "border: 1px solid #2c5236; padding: 4px; }")
        self.resize(420, 460)

        layout = QVBoxLayout(self)
        aviso = QLabel(self._texto_aviso())
        aviso.setObjectName("hint")
        aviso.setWordWrap(True)
        layout.addWidget(aviso)

        self.historico = QPlainTextEdit()
        self.historico.setReadOnly(True)
        self.historico.setMaximumBlockCount(CONVERSA_MAX_LINHAS)    # limite de memória: as mais antigas saem
        layout.addWidget(self.historico, 1)

        self.entrada = QLineEdit()
        self.entrada.setMaxLength(CONVERSA_MAX_ENTRADA)
        self.entrada.setPlaceholderText(f"Escreva para {nome_pet} (até {CONVERSA_MAX_ENTRADA} caracteres)")
        self.entrada.returnPressed.connect(self.enviar)
        layout.addWidget(self.entrada)

        botoes = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        botoes.addWidget(self.status, 1)
        self.botao_cancelar = QPushButton("Cancelar resposta")
        self.botao_cancelar.clicked.connect(self.cancelar)
        self.botao_cancelar.setEnabled(False)
        botoes.addWidget(self.botao_cancelar)
        self.botao_enviar = QPushButton("Enviar")
        self.botao_enviar.setObjectName("start")
        self.botao_enviar.clicked.connect(self.enviar)
        botoes.addWidget(self.botao_enviar)
        layout.addLayout(botoes)

    def _texto_aviso(self):
        """O que acontece com o que você escreve, dito antes da primeira mensagem."""
        destino = ("Suas mensagens SAEM do computador e vão para o provedor do modelo, junto com o nome do pet "
                   "e a emoção dele agora." if self.provedor.envia_para_fora
                   else "Nada sai do computador.")
        return (f"{self.provedor.descricao} {destino} A conversa não é gravada: some ao fechar esta janela. "
                "Ela não muda o cérebro nem a memória do pet.")

    @property
    def ocupado(self):
        """Diz se há uma resposta em andamento."""
        return self._pendente is not None

    def enviar(self):
        """Manda a mensagem digitada para o provedor, numa thread separada (uma por vez)."""
        if self.ocupado:
            return
        try:
            pedido = montar_pedido(self.entrada.text(), self.nome_pet, self.emocao_atual())
        except ValueError as erro:
            self.status.setText(str(erro))
            return
        self._numero += 1
        cancelado = threading.Event()
        self._pendente = (self._numero, cancelado)
        self.entrada.clear()
        self._escrever("Você", pedido.texto)
        self._ocupar(True, f"{self.nome_pet} está pensando...")
        threading.Thread(target=self._rodar, args=(self._numero, pedido, cancelado),
                         name="pestinha-conversa", daemon=True).start()
        self._relogio.start(int(self.tempo_max * 1000))

    def _rodar(self, numero, pedido, cancelado):
        """Na thread do provedor: pede a resposta, valida e devolve pela ponte. Nunca toca na interface."""
        resposta, erro = None, None
        try:
            resposta = validar_resposta(self.provedor.responder(pedido, cancelado))
        except ErroConversa as falha:
            erro = falha
        except Exception as falha:              # provedor com defeito: não derruba o app
            erro = falha
        try:
            self._ponte.terminou.emit(numero, resposta, erro)
        except RuntimeError:
            pass                                # a janela já foi fechada e destruída

    def _terminou(self, numero, resposta, erro):
        """Na thread do Qt: mostra a resposta ou o erro, se este pedido ainda for o atual."""
        if self._pendente is None or self._pendente[0] != numero:
            return                              # cancelado ou passou do tempo: resposta atrasada é ignorada
        self._encerrar()
        if erro is None:
            self._escrever(self.nome_pet, resposta)
            self.status.setText("")
        elif isinstance(erro, ErroConversa):
            self.status.setText(erro.mensagem)
        else:
            log(f"[conversa] erro inesperado do provedor {self.provedor.nome}: {type(erro).__name__}")
            self.status.setText(ErroConversa.mensagem)

    def cancelar(self):
        """Desiste da resposta em andamento; se ela chegar depois, é ignorada."""
        if self._pendente is None:
            return
        self._pendente[1].set()
        self._encerrar()
        self.status.setText("Resposta cancelada.")

    def _estourou(self):
        """Passou do tempo máximo: desiste da resposta."""
        if self._pendente is None:
            return
        self._pendente[1].set()
        self._encerrar()
        self.status.setText(f"Demorou demais (mais de {self.tempo_max:.0f} s). Tente de novo.")

    def _encerrar(self):
        """Fecha a resposta em andamento e libera a caixa de texto."""
        self._pendente = None
        self._relogio.stop()
        self._ocupar(False, "")

    def _ocupar(self, sim, texto):
        """Liga ou desliga os botões enquanto espera a resposta."""
        self.botao_enviar.setEnabled(not sim)
        self.botao_cancelar.setEnabled(sim)
        self.status.setText(texto)

    def _escrever(self, quem, texto):
        """Acrescenta uma fala no histórico da janela (só na memória)."""
        self.historico.appendPlainText(f"{quem}: {texto}")

    def closeEvent(self, event):
        """Ao fechar: cancela o que estiver em andamento e apaga o histórico."""
        self.cancelar()
        self.historico.clear()
        self.fechada.emit()
        super().closeEvent(event)
