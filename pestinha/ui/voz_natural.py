"""
VOZ NATURAL - a tela que confere se o computador aguenta o OmniVoice, explica o que vai ser baixado,
instala (com o andamento na tela) e remove.

A instalação roda em outro processo (python -m pestinha.mind.voz_instalacao --instalar), então a
tela e o pet continuam respondendo durante o download.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import config, plataforma
from ..mind import voz_instalacao
from ..mind.voz_motor import instalada

RAIZ_DO_CODIGO = Path(__file__).resolve().parents[2]       # a pasta que contém o pacote pestinha/
COR = {"ok": "#63e56f", "aviso": "#f2c94c", "falha": "#ff6b6b"}
SIMBOLO = {"ok": "✔", "aviso": "!", "falha": "✖"}

EXPLICACAO = (
    "<p>Com a voz natural, cada pet lê os post-its e os cartazes <b>com a voz dele</b> e <b>com a emoção "
    "do momento</b>: risada quando está feliz, resmungo quando está bravo, suspiro quando está triste.</p>"
    "<p>Tudo roda no seu computador, com o modelo <b>OmniVoice</b>. A internet só é usada agora, para "
    f"baixar uns <b>{voz_instalacao.gb(voz_instalacao.AMBIENTE_GB)}</b> de bibliotecas (PyTorch) e "
    f"<b>{voz_instalacao.gb(voz_instalacao.MODELO_GB)}</b> do modelo, na pasta <code>voz_natural/</code> ao lado do "
    "programa. Depois disso, nada sai do computador.</p>"
    "<p>A fala é gerada antes de o post-it aparecer (uns 6 a 9 segundos): o modelo carrega, gera e é "
    "descarregado, e o áudio é apagado depois de tocar. Sem a voz natural, ele usa a voz do sistema.</p>"
    "<p>A voz de cada pet é o arquivo <code>pets/&lt;pet&gt;/voz/referencia.wav</code>: para trocar, "
    "é só trocar esse arquivo (o README explica como). O modelo tem licença de uso <b>não comercial</b> "
    "(CC BY-NC 4.0).</p>"
)


class VozNaturalDialog(QDialog):
    """Confere o computador, instala e remove a voz natural."""

    mudou = Signal()            # instalou ou removeu: o app liga ou desliga o motor
    vai_mudar = Signal()        # antes de remover: o app fecha o motor (que está usando os arquivos)

    def __init__(self, paths, parent=None, analisar=None, comando=None):
        """`analisar` e `comando` só são trocados nos testes."""
        super().__init__(parent)
        self.paths = paths
        self.pasta = paths.voz_natural
        self._analisar = analisar or (lambda: voz_instalacao.analisar(self.pasta))
        self._comando = comando or [sys.executable, "-u", "-m", "pestinha.mind.voz_instalacao",
                                    "--instalar", "--pasta", str(self.pasta)]
        self.processo = None
        self.setWindowTitle(f"{config.APP_NOME} - voz natural")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        title = QLabel("Voz natural (OmniVoice)")
        title.setObjectName("title")
        root.addWidget(title)
        texto = QLabel(EXPLICACAO)
        texto.setWordWrap(True)
        root.addWidget(texto)

        grupo = QGroupBox("Este computador")
        self.itens_layout = QVBoxLayout(grupo)
        root.addWidget(grupo)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.saida = QPlainTextEdit()
        self.saida.setReadOnly(True)
        self.saida.setMinimumHeight(160)
        self.saida.setVisible(False)
        root.addWidget(self.saida)

        botoes = QHBoxLayout()
        self.remover_btn = QPushButton("Remover")
        self.remover_btn.clicked.connect(self.remover)
        botoes.addWidget(self.remover_btn)
        botoes.addStretch(1)
        self.verificar_btn = QPushButton("Verificar de novo")
        self.verificar_btn.clicked.connect(self.atualizar)
        botoes.addWidget(self.verificar_btn)
        self.instalar_btn = QPushButton("Baixar e instalar")
        self.instalar_btn.setObjectName("start")
        self.instalar_btn.clicked.connect(self.instalar)
        botoes.addWidget(self.instalar_btn)
        self.fechar_btn = QPushButton("Fechar")
        self.fechar_btn.clicked.connect(self.close)
        botoes.addWidget(self.fechar_btn)
        root.addLayout(botoes)
        self.atualizar()

    # ---------------- estado ----------------

    def instalando(self):
        """O download está rodando."""
        return self.processo is not None and self.processo.state() != QProcess.NotRunning

    def atualizar(self):
        """Confere o computador de novo e mostra o resultado."""
        while self.itens_layout.count():
            item = self.itens_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.itens = self._analisar()
        for nome, estado, explicacao in self.itens:
            linha = QLabel(f"<span style='color:{COR[estado]}'>{SIMBOLO[estado]}</span> <b>{nome}</b>: {explicacao}")
            linha.setWordWrap(True)
            self.itens_layout.addWidget(linha)
        pode = voz_instalacao.compativel(self.itens)
        ja = instalada(self.pasta)
        if ja:
            self.status.setText(f"<b>Instalada</b> em {self.pasta}. Ligue \"Falar os bilhetes e cartazes\" "
                                "nas configurações.")
        elif pode:
            self.status.setText("<b>Compatível.</b> Clique em \"Baixar e instalar\" (leva alguns minutos, "
                                "conforme a internet).")
        else:
            sem = ("O pet continua usando a voz do sistema." if plataforma.TEM_VOZ
                   else "Neste sistema, o pet ainda não fala.")
            self.status.setText(f"<b>Este computador não aguenta a voz natural</b> (veja o ✖ acima). {sem}")
        ocupado = self.instalando()
        self.instalar_btn.setVisible(not ja)
        self.instalar_btn.setEnabled(pode and not ocupado)
        self.remover_btn.setVisible(ja or self.pasta.exists())
        self.remover_btn.setEnabled(not ocupado)
        self.verificar_btn.setEnabled(not ocupado)
        self.fechar_btn.setText("Cancelar" if ocupado else "Fechar")

    # ---------------- instalar ----------------

    def instalar(self):
        """Confirma e começa o download, mostrando o andamento."""
        total = voz_instalacao.AMBIENTE_GB + voz_instalacao.MODELO_GB
        if QMessageBox.question(self, "Voz natural", f"Baixar uns {voz_instalacao.gb(total)} e instalar a voz natural?") \
                != QMessageBox.Yes:
            return
        self.saida.clear()
        self.saida.setVisible(True)
        self.processo = QProcess(self)
        self.processo.setProcessChannelMode(QProcess.MergedChannels)
        self.processo.setWorkingDirectory(str(RAIZ_DO_CODIGO))
        self.processo.readyReadStandardOutput.connect(self._ler_saida)
        self.processo.finished.connect(self._terminou)
        self.processo.start(self._comando[0], self._comando[1:])
        self.atualizar()

    def _ler_saida(self):
        """Mostra o que o instalador escreveu."""
        texto = bytes(self.processo.readAllStandardOutput()).decode("utf-8", errors="replace")
        for linha in texto.splitlines():
            if linha.strip():
                self.saida.appendPlainText(linha)

    def _terminou(self, codigo, _status=None):
        """Acabou o download (bem ou mal)."""
        self._ler_saida()
        if codigo == 0 and instalada(self.pasta):
            self.saida.appendPlainText("\nInstalada.")
            self.mudou.emit()
        else:
            self.saida.appendPlainText("\nNão terminou. Pode tentar de novo: ele continua de onde parou.")
        self.atualizar()

    def remover(self):
        """Apaga a voz natural (o pet volta a usar a voz do sistema)."""
        if QMessageBox.question(self, "Voz natural",
                                f"Remover a voz natural? Apaga {self.pasta} (uns 4,5 GB).") != QMessageBox.Yes:
            return
        self.vai_mudar.emit()
        try:
            voz_instalacao.remover(self.pasta)
        except OSError as erro:
            QMessageBox.warning(self, "Voz natural", f"Não deu para apagar tudo: {erro}")
        self.mudou.emit()
        self.atualizar()

    def closeEvent(self, evento):
        """Fechar no meio do download cancela (dá para continuar depois)."""
        if self.instalando():
            if QMessageBox.question(self, "Voz natural", "Cancelar o download? Dá para continuar depois.") \
                    != QMessageBox.Yes:
                evento.ignore()
                return
            self.processo.kill()
            self.processo.waitForFinished(3000)
        super().closeEvent(evento)
