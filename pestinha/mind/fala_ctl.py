"""
FALA CONTROLLER - antes de um post-it, meme ou cartaz aparecer, prepara o que ele vai dizer.

    texto pronto, sem voz natural   aparece na hora (a voz do sistema lê na hora, se a voz estiver ligada)
    texto pronto, com voz natural   fila: gera o áudio (carrega a voz, gera, descarrega) -> aparece com o áudio
    frase nova (IA local)           fila: escreve (carrega o Qwen, escreve, descarrega) -> gera o áudio -> aparece
    comentar a tela (IA com visão)  fila: print -> olha e escreve -> apaga o print -> gera o áudio -> aparece

A fila é a do mind/preparo.py: uma coisa por vez, então a IA e a voz nunca ficam na memória juntas.
Quem pede passa `mostrar(frase)`, chamado na tela quando tudo ficou pronto; ele devolve True se a coisa
apareceu. O áudio que não tocou (desligaram, esconderam ou pausaram no meio) é apagado na hora.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path

from .. import plataforma
from ..log import log
from . import frases_ia, ia_local
from .preparo import Tarefa
from .voz import para_fala

LARGURA_DO_PRINT = 1280         # px: o print é reduzido antes de o modelo olhar (mais rápido, mesmo resultado)


def reduzir_print(caminho, largura=LARGURA_DO_PRINT):
    """Reduz o print (QImage funciona fora da thread da tela). True se a imagem é válida."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    imagem = QImage(str(caminho))
    if imagem.isNull():
        return False
    if imagem.width() > largura:
        imagem = imagem.scaledToWidth(largura, Qt.SmoothTransformation)
    return imagem.save(str(caminho), "PNG")


def arquivo_do_print():
    """Um arquivo novo e privado (só o usuário lê) para o print. Quem usa apaga."""
    descritor, caminho = tempfile.mkstemp(prefix="pestinha-tela-", suffix=".png")
    os.close(descritor)
    return Path(caminho)


def _apagar(caminho):
    if caminho is not None:
        try:
            Path(caminho).unlink(missing_ok=True)
        except OSError:
            pass


def _guardar_copia(origem, copia):
    """Modo teste: guarda o print que a IA vai olhar, para você conferir se a captura deu certo."""
    from PySide6.QtGui import QImage
    try:
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, copia)
        imagem = QImage(str(copia))
        log(f"[espiar] print de {imagem.width()}x{imagem.height()} px; para conferir: {copia} (só no Modo teste)")
    except OSError as erro:
        log(f"[espiar] não guardou a cópia do print: {erro}")


class FalaController:
    """Prepara texto (IA local) e áudio (voz natural) antes de mostrar; mostra na hora quando não há o que preparar."""

    def __init__(self, preparo, voz, pasta_ia, perms, debug, sistema=plataforma, copia_do_print=None):
        """
        `perms` é uma função que devolve as permissões atuais (elas mudam com o programa aberto).
        `copia_do_print`: só no Modo teste, o print que a IA olhou é copiado para lá (para conferir a captura).
        """
        self.preparo = preparo
        self.voz = voz
        self.pasta_ia = Path(pasta_ia)
        self.perms = perms
        self.debug = debug
        self.sistema = sistema
        self.copia_do_print = Path(copia_do_print) if copia_do_print else None

    # ---------------- o que dá para fazer ----------------

    def voz_natural(self):
        """A fala vai ser preparada antes (voz ligada, natural instalada, pet com referência)."""
        return bool(self.perms().get("voz")) and self.sistema.TEM_VOZ and self.voz.natural()

    def ia(self):
        """A IA local está instalada (dá para inventar frases)."""
        return ia_local.instalada(self.pasta_ia)

    def visao(self):
        """A IA local enxerga (dá para comentar a tela)."""
        return ia_local.visao_instalada(self.pasta_ia)

    def ocupado(self):
        """Tem algo sendo preparado (o menu mostra 'Preparando...')."""
        return self.preparo.ocupado()

    # ---------------- escritores (montados na tela, rodam na fila) ----------------

    def escritor(self, nome, personalidade, estado, exemplos=(), evitar=()):
        """Uma frase nova sobre o que ele sente: devolve a função que a fila roda."""
        sistema, pedido = frases_ia.montar(nome, personalidade, estado, exemplos)
        pasta, evitar = self.pasta_ia, tuple(evitar)
        if self.debug():
            log(f"[ia] pedido: {pedido.splitlines()[0]}")
        return lambda controle: frases_ia.escrever(pasta, sistema, pedido, evitar, rodar=controle.rodar)

    def comentador(self, nome, personalidade, estado, imagem=None, capturar=None, copiar_de=None):
        """
        Um comentário sobre uma imagem.
            tela:   `imagem` é o print já tirado (Windows e Linux tiram na tela); sem ela, `capturar(destino)`
                    tira na fila (macOS).
            meme:   `copiar_de` é o meme (ou foto) que ele vai trazer: a IA olha uma cópia, o original fica.
        A imagem que a IA olha é apagada no fim, dê certo ou não.
        """
        if copiar_de is not None:
            sistema, pedido = frases_ia.montar_meme(nome, personalidade, estado)
        else:
            sistema, pedido = frases_ia.montar_visao(nome, personalidade, estado)
        pasta = self.pasta_ia
        copia = self.copia_do_print if self.debug() and copiar_de is None else None   # decidido agora, na tela

        def escrever(controle):
            destino = Path(imagem) if imagem is not None else arquivo_do_print()
            try:
                if copiar_de is not None:
                    shutil.copyfile(copiar_de, destino)
                elif imagem is None and not capturar(destino):
                    return None, "não conseguiu tirar o print da tela (permissão de Gravação de Tela?)"
                if not reduzir_print(destino):
                    return None, "a imagem veio vazia"
                if copia is not None:
                    _guardar_copia(destino, copia)
                return frases_ia.comentar(pasta, sistema, pedido, destino, rodar=controle.rodar)
            finally:
                _apagar(destino)
        return escrever

    # ---------------- preparar e mostrar ----------------

    def precisa_preparar(self, escrever=None, texto=None):
        """Há algo a preparar antes de mostrar (escrever com a IA, ou gerar a fala natural de um texto falável)."""
        if escrever is not None:
            return True
        return self.voz_natural() and (texto is None or bool(para_fala(texto)))

    def preparar(self, rotulo, mostrar, texto=None, escrever=None, emocao=None, ao_falhar=None, ao_cancelar=None):
        """
        Põe na fila: escreve (se `escrever`), gera a fala (se a voz natural estiver valendo) e chama
        `mostrar(frase)` na tela. Devolve False se a fila estava cheia.
        """
        natural = self.voz_natural()
        voz, debug = self.voz, self.debug

        def trabalho(controle):
            inicio = time.monotonic()
            frase = texto
            if escrever is not None:
                frase, motivo = escrever(controle)
                if not frase:
                    raise RuntimeError(motivo or "não escreveu nada")
            escreveu = time.monotonic()
            arquivo = voz.preparar(frase, emocao, rodar=controle.rodar) if natural else None
            return frase, arquivo, escreveu - inicio, time.monotonic() - escreveu

        def ao_terminar(resultado):
            frase, arquivo, t_texto, t_voz = resultado
            partes = ([f"escreveu em {t_texto:.1f} s"] if escrever is not None else []) + (
                [f"voz em {t_voz:.1f} s" if arquivo else "sem voz natural"] if natural else [])
            log(f"[preparo] {rotulo}: " + ", ".join(partes or ["pronto"])
                + (f": {frase!r}" if debug() else ""))
            if arquivo is not None:
                voz.anexar(frase, arquivo)
            try:
                mostrar(frase)
            finally:
                voz.descartar(frase)            # não tocou (não apareceu ou a voz foi desligada): apaga

        def descartar(resultado):
            _apagar(resultado[1])

        def falhou(motivo):
            log(f"[preparo] {rotulo}: não deu ({motivo})")
            if ao_falhar is not None:
                ao_falhar(motivo)

        return self.preparo.pedir(Tarefa(rotulo, trabalho, ao_terminar, falhou, descartar, ao_cancelar))
