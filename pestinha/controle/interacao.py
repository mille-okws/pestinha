"""
INTERAÇÃO - o que você faz com o pet: cutucar, arrastar, arremessar, dispensar travessuras,
os comandos do menu do botão direito e o notebook.

Cada interação vira sinal para a rede (sentidos), homeostase, condicionamento e memória.
Pausado ou desligado, as interações não mexem no estado (ver SessaoMixin._congelado).
Mixin de PestinhaApp: usa os atributos criados em PestinhaApp.__init__.
"""

from ..log import log
import random
import time
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from .. import config, plataforma
from ..mind import frases_ia
from ..mind.fala_ctl import arquivo_do_print
from ..body.pet import cursor_pos
from ..ajustes import (
    INSATISFACAO_NOTEBOOK,
    COOLDOWN_CUTUCADA as POKE_COOLDOWN,
    ESPERA_MEDIDA_CUTUCADA as POKE_PROBE,
    HZ_RESPOSTA_CHEIA as POKE_FULL_HZ,
    RESPOSTA_MINIMA as POKE_MIN_RESPONSE,
)


class InteracaoMixin:
    """Ações do usuário sobre o pet: cutucar, arrastar, arremessar, dispensar travessuras e o menu do botão direito. Vira atributo de PestinhaApp."""
    def on_poke(self):
        """Você cutucou o pet: ele reage e a rede recebe o toque (ignorado na pausa)."""
        if self._congelado():
            return
        now = time.monotonic()
        if now - self.last_poke < POKE_COOLDOWN:
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.25)     # cutucar alegra um pouco
        self.last_poke = now
        self.conditioning.outcome(now)
        self.senses.poke()
        self.timeline.note_interaction()
        self.drives.stimulate("poke")
        self.drives.touched("poke")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)
        # a reação NÃO é fixa: mede-se o que a rede fez com a cutucada (ver poke_reflex)
        self.poke_probe = (now + POKE_PROBE, self.brain.motor_activity()["CHEER"])

    def poke_reflex(self, delta_hz):
        """
        Tamanho da reação = aumento real de CHEER causado pela cutucada.
        Com cutucadas repetidas a sinapse de POKE habitua e a resposta encolhe:
        pulo grande, pulo menor, só os olhos, quase nada. Volta depois de minutos.
        """
        self.poke_probe = None
        response = max(0.0, min(1.0, delta_hz / POKE_FULL_HZ))
        if self.protest.stage == 3:
            response *= 0.2                         # em greve: mal responde
        self.last_poke_response = response
        body = self.pet.body
        if response >= POKE_MIN_RESPONSE and body.grounded:
            body.jump(0.0, -(150.0 + 650.0 * response))
        else:
            self.pet_state.blink_until = time.monotonic() + 0.13       # só pisca e olha
            cx, cy = cursor_pos()
            self.behavior.look_at(cx, cy, time.monotonic())
        if self.debugging():
            eff = self.brain.efficacy()["POKE"]
            log(f"[cutucada] resposta da rede {response:.2f} "
                  f"(+{delta_hz:.1f} Hz em CHEER, eficácia POKE {eff:.2f})")

    def on_drag_started(self):
        """Você pegou o pet: ele sente o arraste e a insatisfação baixa um pouco (você está interagindo)."""
        if self._congelado():
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.1)
        self.conditioning.outcome(time.monotonic())
        self.senses.set_dragging(True)
        self.timeline.note_interaction()
        self.drives.stimulate("drag")
        self.drives.touched("drag")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)

    def on_thrown(self, speed):
        """Você arremessou o pet: a velocidade vira intensidade do arremesso; ele não aprende com isso na pausa."""
        if self._congelado():
            return
        self.conditioning.outcome(time.monotonic())
        self.senses.thrown(min(1.0, speed / 2000.0))
        self.timeline.note_interaction()
        self.drives.stimulate("throw")
        self.drives.touched("throw")
        self.in_flight = True

    def on_dismissed(self, thing, elapsed):
        """Você dispensou uma travessura: ela some, e o tempo até você fechar vira aprendizado (fechar rápido é pior)."""
        if getattr(thing, "fala", None):
            self.voz.parar(thing.fala)               # fechou o post-it (ou meme) que ele estava falando: ele para
        if self._congelado():
            return                                   # o objeto some, mas não vira aprendizado na pausa
        self.mischief_ctl.on_dismissed(thing, elapsed, self.prof, time.monotonic())

    def arrancar_notebook(self, now):
        """Arrancaram o notebook dele: ele levanta e fica bravo ou triste, conforme o pet."""
        self.mesa.levantar_arrancado(now)
        self.senses.dismissed()                    # a dispensa entra na rede como frustração
        alvo = self.sad_ctl if self.reacao_notebook == "triste" else self.protest_ctl
        alvo.provoke(INSATISFACAO_NOTEBOOK)
        if self.debugging():
            log(f"[notebook] arrancado: reação {self.reacao_notebook}")

    def show_pet_menu(self, pos):
        """Mostra o menu do botão direito no pet; cada item fica desativado se não fizer sentido agora."""
        menu = QMenu()
        perms = self.perms

        def item(text, fn, enabled=True):
            """Cria um item do menu; `enabled=False` deixa o item visível mas sem ação."""
            act = menu.addAction(text)
            act.setEnabled(enabled)
            act.triggered.connect(fn)

        item("Cutucar", self.menu_poke, perms["cutucar"])
        item("Dar carinho", self.menu_caress, perms["carinho"])
        menu.addSeparator()
        item("Jogar a bolinha perto dele", self.menu_place_ball, perms["bolinha"])
        item("Guardar a bolinha", self.menu_store_ball, perms["bolinha"] and not self.ball_stored)
        menu.addSeparator()
        item("Pedir para dormir", self.menu_sleep, not self.asleep)
        item("Pedir para trabalhar", self.menu_pedir_trabalho)
        item("Mostrar o notebook" if self.mesa.escondido else "Esconder o notebook",
             self.menu_alternar_notebook)
        item("Fazer uma travessura agora", self.menu_mischief, perms["travessuras"])
        pode_bilhete = perms["travessuras"] and perms["bilhetes"]
        if self.fala.ocupado():
            fila = self.preparo.rotulos()
            item(f"Preparando: {fila[0]}..." if fila else "Preparando...", lambda: None, False)
        elif self.fala.ia():
            item("Escrever o que está sentindo (IA)", self.menu_frase_ia, pode_bilhete)
            if self.fala.visao():
                item("Espiar a tela e comentar (IA)", self.menu_espiar, pode_bilhete)
        if self.debugging() and self.paths.ultima_espiada.exists():
            item("Ver o último print (teste)", self.menu_ver_print)
        else:
            item("Escrever o que está sentindo (IA não instalada)", lambda: None, False)
        menu.addSeparator()
        item("Cantinho do castigo", lambda: self.castigo.toggle(self.bounds()))
        for chave, nome in (("greve", "painel de protesto"), ("neural", "monitor neural")):
            # o painel fica atrás quando você usa outro programa: clicar traz para a frente
            # *_: o triggered do Qt manda o `checked` como primeiro argumento
            item(nome[0].upper() + nome[1:], lambda *_, k=chave: self.floats.open(k))
            if chave in self.floats.opened or self.floats.aberto(chave):
                item(f"Fechar o {nome}", lambda *_, k=chave: self.floats.close(k))
        item("Configurações...", self.open_settings)
        menu.addSeparator()
        item("Sair", self.quit)                 # fecha o programa (igual ao Sair da bandeja)
        menu.exec(pos)

    def menu_poke(self):
        """Menu: 'Cutucar' (ignora o intervalo mínimo entre cutucadas)."""
        self.last_poke = 0.0
        self.on_poke()

    def menu_caress(self):
        """Menu: 'Fazer carinho' (conta como carinho na rede, se não estiver pausado)."""
        if self._congelado():
            return
        self.pet_state.mark_caress()
        self.drives.touched("caress")
        self.memory.on_interaction()
        self.timeline.note_interaction()

    def menu_place_ball(self):
        """Menu: 'Pôr a bolinha' (coloca a bolinha perto do pet, no chão)."""
        self.ball_stored = False
        self.ball.body.x = self.pet.body.x + 130
        self.ball.body.y = self.bounds()[3] - 40
        self.ball.body.vx = self.ball.body.vy = 0.0
        self.update_visibility()

    def menu_store_ball(self):
        """Menu: 'Guardar a bolinha' (some com a bolinha até você pedir de novo)."""
        self.ball_stored = True
        self.update_visibility()

    def menu_sleep(self):
        """Menu: 'Dormir' (baixa a energia: ele cochila em vez de ficar acordado)."""
        if self._congelado():
            return
        self.drives.energy = min(self.drives.energy, 0.1)

    def menu_mischief(self):
        """Menu: 'Aprontar' (pede uma travessura agora)."""
        self.mischief_ctl.pedir(time.monotonic())

    # ---------------- IA local e fala preparada (em teste) ----------------

    def estado_para_ia(self):
        """O que a rede sente agora, do jeito que entra no pedido da IA (só a categoria do programa)."""
        sentidos = self.drives.channels()
        return {"emocao": self.pet_state.emotion, "cansaco": sentidos["FATIGUE"],
                "carencia": sentidos["LONELY"], "tedio": sentidos["BOREDOM"], "atividade": self.activity,
                "protesto": self.protest.stage, "hora": time.localtime().tm_hour}

    def escritor_ia(self, emocao=None, acao="bilhete"):
        """Monta (na tela) o pedido de uma frase nova; a fila do preparo é quem escreve."""
        triste = acao == "bilhete_triste" or (emocao or self.pet_state.emotion) == "triste"
        notas = self.mischief.notes_sad if triste else self.mischief.notes
        notas.has_lines()                                       # relê o arquivo se mudou
        exemplos = random.sample(notas.lines, min(frases_ia.EXEMPLOS, len(notas.lines)))
        return self.fala.escritor(self.nome, self.personalidade, self.estado_para_ia(), exemplos,
                                  evitar=notas.lines)

    def _pode_entregar(self, acao="bilhete"):
        """Algo preparado (post-it, meme, foto) ainda pode aparecer: não desligaram, esconderam nem pausaram no meio."""
        perms = self.perms
        permissao = "fotos" if acao == "foto" else "memes" if acao.startswith("meme") else "bilhetes"
        return (perms["ativo"] and perms["travessuras"] and perms[permissao] and self.pet.isVisible()
                and not self._congelado() and not self.castigo.dentro)

    def _pode_entregar_bilhete(self):
        """Um post-it preparado ainda pode aparecer."""
        return self._pode_entregar("bilhete")

    def testar_meme(self, com_ia=False):
        """Configurações: traz um meme agora, para testar (com a fala, se a voz estiver ligada)."""
        if not self.pet.isVisible() or self._congelado():
            aviso = f"{self.nome} está escondido ou pausado."
        elif self.asleep:
            aviso = f"{self.nome} está dormindo."
        elif self.castigo.dentro:
            aviso = f"{self.nome} está de castigo."
        elif self.mischief_ctl.pendente is not None or self.preparo.ocupado():
            aviso = f"{self.nome} já está preparando outra coisa. Tente de novo daqui a pouco."
        else:
            now, bounds, cursor = self._cena()
            aviso = self.mischief_ctl.testar_meme(self.pet_state.emotion, now, bounds, cursor, com_ia)
        log(f"[teste] meme{' com IA' if com_ia else ''}: {aviso}")
        if self.settings is not None:
            self.settings.aviso_teste(aviso)
        return aviso

    def comentador_de_imagem(self, emocao, imagem):
        """Monta (na tela) o pedido para a IA comentar o meme ou foto que ele vai trazer."""
        return self.fala.comentador(self.nome, self.personalidade, self.estado_para_ia(), copiar_de=imagem)

    def _cena(self):
        """(agora, área da tela, cursor) na hora em que algo preparado aparece."""
        return time.monotonic(), self.bounds(), cursor_pos()

    def _preparar_cartaz(self, rotulo, emocao, texto, pronto, falhou, cancelado):
        """Cartaz novo: com a voz natural, gera a fala antes (o cartaz espera); sem ela, False (aparece já)."""
        if not self.fala.precisa_preparar(texto=texto) or not self.pet.isVisible() or self._congelado():
            return False                                        # "@#$%!" não tem o que falar: aparece já
        return self.fala.preparar(rotulo, pronto, texto=texto, emocao=emocao,
                                  ao_falhar=falhou, ao_cancelar=cancelado)

    def _bilhete_ia(self, rotulo, escrever, ao_cancelar=None):
        """Põe na fila: a IA escreve, a voz gera, e o post-it aparece (pedido pelo menu ou pela vontade de espiar)."""
        def mostrar(frase):
            if not self._pode_entregar_bilhete():
                log(f"[preparo] {rotulo}: ficou pronto, mas agora não pode aparecer")
                return False
            now, bounds, cursor = self._cena()
            if self.mischief_ctl.mostrar_bilhete(frase, now, bounds, cursor, andar=not self.asleep) is None:
                log(f"[preparo] {rotulo}: não achou lugar para o post-it")
                return False
            return True

        def falhou(motivo):
            self.tray.icon.showMessage(config.APP_NOME, f"{self.nome} não conseguiu escrever agora ({motivo}).",
                                       QSystemTrayIcon.Information, 4000)
        if not self.fala.preparar(rotulo, mostrar, escrever=escrever, emocao=self.pet_state.emotion,
                                  ao_falhar=falhou, ao_cancelar=ao_cancelar):
            if ao_cancelar is not None:
                ao_cancelar()
            log(f"[preparo] {rotulo}: a fila está cheia")
            return False
        return True

    def menu_frase_ia(self):
        """Menu: 'Escrever o que está sentindo (IA)'. A rede diz o que ele sente; a IA local escreve."""
        self._bilhete_ia("frase pedida no menu", self.escritor_ia())

    # ---------------- espiar a tela (IA local com visão, em teste) ----------------

    def pode_espiar(self):
        """As regras para espiar sozinho: permissões, visão instalada, o sistema deixa, e ele está livre."""
        perms = self.perms
        return (perms["ver_tela"] and perms["ativo"] and perms["travessuras"] and perms["bilhetes"]
                and not self.fullscreen and not self.asleep and self.protest.stage < 3 and self.sad.stage < 2
                and self.pet.isVisible() and not self._congelado() and not self.castigo.dentro
                and self.fala.visao() and plataforma.permissao_tela())

    def maybe_espiar(self, now, dt, motores):
        """O neurônio ESPIAR decide quando; aqui só as regras (e uma coisa por vez na fila)."""
        if not self.perms["ver_tela"] or self.fala.ocupado() or self.mischief_ctl.pendente is not None:
            return
        if not self.espiar.quer(now, dt, motores["ESPIAR"]) or not self.pode_espiar():
            return
        self.espiar.espiou(now)
        if self.debugging():
            log(f"[espiar] ESPIAR {motores['ESPIAR']:.1f} Hz: vai espiar a tela")
        self.espiar_agora("espiada na tela")

    def menu_espiar(self):
        """Menu: 'Espiar a tela e comentar (IA)'. Clicar é pedir: vale mesmo com o espiar sozinho desligado."""
        if not plataforma.permissao_tela():
            plataforma.pedir_permissao_tela()           # abre a pergunta do sistema (macOS), uma vez
            self.tray.icon.showMessage(
                config.APP_NOME, f"Para {self.nome} espiar a tela, permita a Gravação de Tela para este programa "
                "(Ajustes do Sistema > Privacidade e Segurança > Gravação de Tela). Depois, feche e abra de novo "
                "o programa (rodando pelo código, o Terminal): o macOS só vale a permissão ao reabrir.",
                QSystemTrayIcon.Information, 8000)
            return
        self.espiar.espiou(time.monotonic())
        self.espiar_agora("espiada pedida no menu")

    def menu_ver_print(self):
        """Menu (Modo teste): abre a cópia do último print que a IA olhou, no visualizador do sistema."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.ultima_espiada)))

    def espiar_agora(self, rotulo):
        """Tira o print (no macOS, na fila; nos outros, aqui na tela), e a IA comenta. O print é apagado depois."""
        estado = self.estado_para_ia()
        if plataforma.CAPTURA_EM_QUALQUER_THREAD:
            escrever = self.fala.comentador(self.nome, self.personalidade, estado, capturar=plataforma.capturar_tela)
            return self._bilhete_ia(rotulo, escrever)
        destino = arquivo_do_print()
        apagar = lambda: destino.unlink(missing_ok=True)       # noqa: E731
        if not plataforma.capturar_tela(destino):
            apagar()
            log(f"[espiar] {rotulo}: não conseguiu tirar o print")
            return False
        return self._bilhete_ia(rotulo, self.fala.comentador(self.nome, self.personalidade, estado, imagem=destino),
                                ao_cancelar=apagar)

    def menu_alternar_notebook(self):
        """Menu: mostra ou esconde o notebook; sem o notebook, ele não pode sentar nele."""
        self.mesa.alternar_notebook()
        self.pet_state.at_desk = self.mesa.sentado
        if not self.mesa.sentado:
            self.pet_state.desk_top = None

    def menu_pedir_trabalho(self):
        """Menu: 'Pedir para trabalhar' (ele pode aceitar, ou recusar com frustração)."""
        self.mesa.pedir(time.monotonic())
