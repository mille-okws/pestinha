"""
SESSÃO - o que vale para a sessão inteira: permissões, visibilidade, pausa, pânico,
salvar, sair e apagar os dados.

Política única: pausado, desligado (pânico) ou apagando os dados, nada de rede, sentidos ou
decisões (`_congelado`). Desligado ou coberto por tela cheia, nada fica na tela (`update_visibility`).
Mixin de PestinhaApp: usa os atributos criados em PestinhaApp.__init__.
"""

from .. import log as log_module
from ..log import log
import time
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from .. import config, plataforma, store
from ..ui.ui import SettingsDialog


class SessaoMixin:
    """Ciclo de vida da sessão: ligar e desligar, pausar, esconder, pânico, salvar e sair. Vira atributo de PestinhaApp."""
    def _congelado(self):
        """Pausado, desligado (pânico) ou apagando os dados: nada de rede, sentidos ou decisões."""
        return self.paused or not self.perms["ativo"] or self.wiping

    def apply_perms(self, new):
        """Chamado pela tela de configurações: aplica e grava na hora."""
        was_routine = self.perms["rotina"]
        self.store.update(new)
        if was_routine and not self.perms["rotina"]:
            self.timeline.close()      # grava o minuto em andamento e para
        self.prof = config.profile(self.perms)
        self.conditioning.rate = self.prof["cond_rate"]
        if not self.perms["voz"]:
            self.voz.desligar()                      # cala e apaga os áudios prontos
        if not self.perms["modo_teste"]:
            self.paths.ultima_espiada.unlink(missing_ok=True)    # saiu do Modo teste: a cópia do print some
        if new.get("ver_tela") and not plataforma.permissao_tela():
            plataforma.pedir_permissao_tela()        # você ligou agora: o macOS pergunta (só uma vez)
        self._apply_settings()

    def _apply_settings(self):
        """Aplica as permissões atuais: o que mostrar, quais painéis e o estado do pet."""
        st = self.pet_state
        st.show_label = self.perms["modo_teste"] and self.perms["mostrar_emocao"]
        st.allow_drag = self.perms["arrastar"]
        st.allow_poke = self.perms["cutucar"]
        self._atualizar_parada()
        self.update_visibility()

    def _voz_natural_vai_mudar(self):
        """Vão remover a voz natural pelo menu: para o que está sendo preparado, que usa os arquivos."""
        self.preparo.cancelar()
        self.voz.desligar()

    def _voz_natural_mudou(self):
        """Instalaram ou removeram a voz natural pelo menu: a próxima fala já usa (ou não) a voz natural."""

    def floats_allowed(self):
        """Painéis abertos sozinhos: só no modo teste, com "Abrir os painéis no modo teste" ligado."""
        return self.perms["modo_teste"] and self.perms["paineis_teste"] and self.floats_base()

    def floats_base(self):
        """Painéis abertos à mão: só some se o pet estiver desligado ou coberto por tela cheia."""
        return self.perms["ativo"] and (not self.fullscreen or self.perms["tela_cheia"])

    def update_visibility(self):
        """Decide se o pet aparece (ligado, não escondido, sem tela cheia, sem pânico) e mostra ou esconde tudo junto."""
        visible = self.perms["ativo"] and (not self.fullscreen or self.perms["tela_cheia"])
        if visible != self.pet.isVisible():
            self.pet.setVisible(visible)
            if not visible:
                self.behavior.drop_carried()
                self.pet.cancel_interaction()        # escondido ou desligado no meio do arraste
                self.senses.set_dragging(False)
        self.mischief.set_visible(visible)
        if not visible:
            self.voz.parar()                         # escondido, desligado ou em tela cheia: calado
        if not self.perms["travessuras"] and self.mischief.things:
            self.clear_things()                      # travessuras desligadas: o que estava na tela sai
        self.mesa.set_visible(visible)
        self.castigo.set_visible(visible)
        if not visible:
            self.revolucao.esconder()
        self.floats.sync(self.floats_allowed(), self.floats_base())
        self.protest_ctl.set_visible(visible, self.asleep)
        self.sad_ctl.set_visible(visible, self.asleep)
        if not visible:
            self.castigo.pausar(self.pet_state)
        bola_visivel = visible and self.perms["bolinha"] and not self.ball_stored
        if not bola_visivel:
            self.ball.cancel_drag()                  # guardada ou escondida na mão: larga
        self.ball.setVisible(bola_visivel)
        if not visible or not self.perms["fogos"]:
            self.festa.fogos.recolher()
        self.tray.set_state(self.paused, self.perms["modo_teste"])

    def open_settings(self):
        """Abre a tela de configurações (ou traz para frente se já estiver aberta)."""
        if not (self.settings and self.settings.isVisible()):
            self.settings = SettingsDialog(self.perms, self.paths, first_run=False)
            self.settings.changed.connect(self.apply_perms)
            self.settings.wipe_all.connect(self.wipe_all_data)
            self.settings.history_wiped.connect(self.timeline.discard)
            self.settings.voz_natural_vai_mudar.connect(self._voz_natural_vai_mudar)
            self.settings.voz_natural_mudou.connect(self._voz_natural_mudou)
            self.settings.testar_meme.connect(self.testar_meme)
            self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()      # veio do pet ou da bandeja: o programa pode nem estar ativo

    def toggle_floating(self):
        """Mostra ou esconde os painéis de teste."""
        self.floats.toggle_tray(self.floats_allowed(), self.floats_base())

    def toggle_pause(self):
        """Pausa ou retoma: na pausa a rede e os sentidos param, e os prazos são empurrados para não 'vencerem' de uma vez."""
        self.paused = not self.paused
        if self.paused:
            self.voz.parar()
        self._atualizar_parada()
        self.festa.fogos.pausar(self.paused)
        self.update_visibility()

    def _atualizar_parada(self):
        """Marca quando o pet parou (pausa ou pânico) e, ao voltar, empurra os prazos pelo tempo parado."""
        now = time.monotonic()
        parado_agora = self.paused or not self.perms["ativo"]
        if parado_agora:
            if self._pausado_em is None:
                self._pausado_em = now
        elif self._pausado_em is not None:
            parado = now - self._pausado_em
            self.memory.deslocar(parado)                     # o tempo parado não expira episódios
            self.castigo.deslocar(parado)                    # nem a fuga, a entrada e o cartaz
            self.mesa.deslocar(parado)                       # nem o pedido de trabalho
            self.conditioning.deslocar(parado)               # nem as janelas de condicionamento
            self._pausado_em = None
            self._ultimo_think = now                         # a retomada não cobra o tempo parado

    def clear_things(self):
        """Tira as travessuras que estão na tela."""
        self.mischief_ctl.clear()

    def panic(self):
        """Desliga tudo e grava: só volta quando você religar na tela inicial."""
        self.store.panic()
        self.preparo.cancelar()                      # mata a IA e a voz que estavam preparando
        self.voz.desligar()
        self._atualizar_parada()
        self.pet.cancel_interaction()
        self.clear_things()
        self.protest_ctl.drop_sign()
        self.sad_ctl.drop_sign()
        if self.settings:
            self.settings.set_active(False)
        self.update_visibility()
        self.tray.icon.showMessage(
            config.APP_NOME, f"Pânico: {config.APP_NOME} desligado. Religue em Configurações.",
            QSystemTrayIcon.Warning, 4000,
        )

    def wipe_all_data(self):
        """Apaga a pasta memory/ inteira e fecha. Nada é gravado depois disso, nem o log."""
        self.wiping = True
        self.preparo.cancelar()                      # o motor da voz escreve no log de memory/
        self.voz.desligar()
        log_module.desligar_arquivo()
        falhas = store.apagar_pasta(self.paths.memory) if self.paths.memory.exists() else []
        if falhas or self.paths.memory.exists():
            print(f"[dados] não consegui apagar tudo: {falhas or self.paths.memory}")
            lista = "\n".join(falhas[:5]) or str(self.paths.memory)
            QMessageBox.warning(
                self.settings, "Não foi possível apagar tudo",
                f"Alguns dados continuam em {self.paths.memory}. O programa vai fechar; feche o que possa "
                f"estar usando esses arquivos e tente de novo.\n\nArquivos que falharam:\n{lista}",
            )
        else:
            print("[dados] tudo apagado pelo usuário")
        self.quit()

    def save(self):
        """Grava o estado do pet e do app (não grava depois de 'apagar tudo')."""
        if self.wiping:
            return
        for nome, gravar in (
            ("o cérebro", lambda: self.brain.save(str(self.state_file))),
            ("a homeostase", lambda: self.drives.save(self.pet_paths.drives)),
            ("a memória", self.memory.save),
            ("o cantinho", self.castigo.salvar),
            ("o condicionamento", self.conditioning.save),
            ("o protesto", self.protest_ctl.save),
            ("a tristeza", self.sad.save),
        ):
            try:
                gravar()
            except Exception as error:       # uma parte com problema não impede as outras nem o fechamento
                log(f"[app] não salvou {nome}: {error}")
        if self.perms["modo_teste"]:
            sleeping = "  (dormindo)" if self.asleep else ""
            log(f"[homeostase] {self.drives.describe()}{sleeping}")
            log("[condicionamento] " + "  ".join(f"{k} {v:.2f}" for k, v in self.conditioning.V.items()))
            learned = self.brain.learned_summary()
            if learned:
                log("[aprendizado] " + "  ".join(f"{c}->{post} {w:+.3f}" for c, post, w in learned))

    def quit(self):
        """Salva tudo e fecha o programa; um erro no caminho nunca impede de fechar."""
        try:
            self.preparo.cancelar()
            self.voz.desligar()
            self.save()
            self.mesa.fechar()
            self.festa.fechar()
            self.revolucao.fechar()
            if not self.wiping:
                self.protest_ctl.drop_sign()
                self.sad_ctl.drop_sign()
                if self.perms["rotina"]:
                    self.timeline.close()
                self.mischief.clear()
        except Exception as error:
            log(f"[app] erro ao fechar: {error}")
        finally:
            self.tray.icon.hide()
            QApplication.quit()
