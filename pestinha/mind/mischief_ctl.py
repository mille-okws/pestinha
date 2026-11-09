"""
MISCHIEF CONTROLLER - quando e como ele apronta, e o que a dispensa causa.

As regras dizem o que PODE (permissões, tela cheia, limite de objetos, assets,
triste e dormindo não aprontam). A memória episódica escolhe o que FAZER,
pelo que deu certo antes naquele contexto. A dispensa alimenta a rede (raiva),
a memória (episódio negativo) e o aprendizado (penalidade de 1 s).

Post-it: o motor INVENTAR da rede decide se a frase é nova (escrita pela IA local)
ou uma já escrita de recadinhos.txt. Se houver algo a preparar (a frase nova, a
fala da voz natural), o post-it espera a fila do mind/preparo.py e aparece depois,
já com o áudio; enquanto isso, ele não apronta outra.
"""

from ..log import log
import random
from collections import deque
from pathlib import Path

VALIDADE_PEDIDO_S = 10.0    # s: "fazer uma travessura agora" vale por este tempo

from ..core.emotion import PRIORITY
from ..ajustes import (DISPENSA_RAPIDA as QUICK_DISMISS, PENALIDADE_DISPENSA as PENALTY_SECONDS,
                       GANHO_TRAVESSURA, INVENTAR_TAXA_CHEIA_HZ)

BILHETES = ("bilhete", "bilhete_canto", "bilhete_triste")
IMAGENS = ("meme", "meme_canto", "meme_trabalho", "foto")         # com a voz ligada, ele fala ao trazer


def chance_de_inventar(taxa_hz):
    """Taxa do motor INVENTAR -> chance de a frase do post-it ser nova (0 a 1)."""
    return max(0.0, min(1.0, taxa_hz / INVENTAR_TAXA_CHEIA_HZ))



class MischiefController:
    """Decide quando aprontar (memes, bilhetes, fotos) e reage quando você dispensa ou pega esses objetos."""
    def __init__(self, engine, memory, drives, senses, behavior, emotion, debug):
        """Guarda os colaboradores: o motor de travessuras, a memória, as necessidades e o corpo."""
        self.engine = engine
        self.memory = memory
        self.drives = drives
        self.senses = senses
        self.behavior = behavior
        self.emotion = emotion
        self.debug = debug
        self.dismiss_times = deque()
        self.postit_weight = 0.5     # quanto o pet gosta de colar post-its (ligado pelo app)
        self.penalty_until = 0.0
        self.pedido_forcado = False     # "fazer uma travessura agora": ignora o sorteio uma vez
        self.forcado_ate = 0.0
        # post-its preparados antes de aparecer (ligados pelo app; sem eles, tudo aparece na hora)
        self.fala = None                # FalaController: prepara frase nova e fala natural
        self.escritor = None            # (emoção, ação) -> função que escreve com a IA (monta o pedido na tela)
        self.pode_inventar = lambda: False      # IA local instalada e "Inventar frases novas" ligado
        self.pode_entregar = lambda acao: True  # na hora de aparecer: ainda pode? (desligaram, esconderam...)
        self.cena = None                # () -> (now, bounds, cursor) na hora de aparecer
        self.pendente = None            # o post-it (ou meme) que está sendo preparado (um por vez)
        # memes e fotos com fala (só com a voz ligada; sem ela, continuam mudos)
        self.pode_falar = lambda: False         # a voz está ligada
        self.pode_ver = lambda: False           # IA local com visão e "Inventar frases novas" ligado
        self.comentador = None                  # (emoção, imagem) -> função que comenta a imagem com a IA

    def pedir(self, now):
        """O comando do menu: a próxima tentativa acontece, se as regras permitirem, nos próximos segundos."""
        self.pedido_forcado = True
        self.forcado_ate = now + VALIDADE_PEDIDO_S

    def penalty_active(self, now):
        """Diz se ainda está valendo a penalidade por ter sido dispensado (ele não apronta de novo logo)."""
        return now < self.penalty_until

    def maybe_act(self, now, dt, bounds, cursor, body, *, motores, activity, emotion, perms, prof,
                  fullscreen, asleep, protest_stage, working=False):
        """
        Tenta uma travessura neste quadro. A frequência é o disparo do neurônio TRAVESSURA:
        quanto mais ele dispara, mais travessuras por segundo. Devolve a ação escolhida, ou None.
        """
        if self.pedido_forcado and now > self.forcado_ate:
            self.pedido_forcado = False                # o pedido do menu venceu sem dar certo
        if not self.pedido_forcado and random.random() >= motores.get("TRAVESSURA", 0.0) * GANHO_TRAVESSURA * dt:
            return None
        if self.pendente is not None and (self.fala is None or not self.fala.ocupado()):
            self.pendente = None                     # a fila foi esvaziada sem avisar (não deveria)
        if body.held or not body.grounded or self.behavior.mission or self.pendente is not None:
            return None
        if asleep or protest_stage == 3 or not self.engine.allowed(perms, prof, fullscreen):   # greve para tudo; reclamação/manifestação não param os post-its
            return None

        ctx = self.memory.context(activity, emotion)
        options = self.engine.available(emotion, perms, working=working)
        if self.postit_weight <= 0:                  # peso zero: post-its (bilhetes) ficam desligados
            options = [o for o in options if not o.startswith("bilhete")]
        if protest_stage == 4:                       # revolução: só traz fotinhas bravas
            if "meme" not in options:
                return None
            action = "meme"
        else:
            action = self.memory.choose(ctx, options, prof["explore"])
        if action is None or action not in options:
            return None
        self.pedido_forcado = False
        # pet 'postit' prefere colar post-its quando pode
        boost = 1.8 if emotion == "feliz" else 1.0     # feliz cola mais post-its
        if self.postit_weight > 0 and random.random() < 0.5 * self.postit_weight * boost:
            for cand in (("bilhete_canto", "bilhete") if emotion == "bravo" else ("bilhete",)):
                if cand in options:
                    action = cand
                    break
        if self.debug() and self.memory.last_choice:
            log(f"[escolha] {ctx} -> {action} ({self.memory.last_choice[2]})")

        if action in BILHETES:
            return self._bilhete(action, ctx, emotion, motores, now, bounds, cursor)
        plan = self.engine.plan(action, emotion)
        thing = plan[1] if plan else None
        if action in IMAGENS and thing is not None and self.pode_falar():
            return self._imagem(action, plan, ctx, emotion, motores, now, bounds, cursor)
        if plan and plan[0] == "corner":
            if not self.engine.show_in_corner(thing, bounds, cursor):
                return None
        elif plan:
            self.behavior.start_mission(plan, bounds, cursor, now)
        elif action != "nada":
            return None
        self.memory.start(ctx, action, thing)
        if action != "nada":
            self.drives.stimulate("mischief")
        return action

    # ---------------- post-its (frase nova ou já escrita; fala preparada antes) ----------------

    def _bilhete(self, action, ctx, emotion, motores, now, bounds, cursor):
        """A rede decide a frase (INVENTAR); se houver o que preparar, o post-it espera a fila."""
        taxa = motores.get("INVENTAR", 0.0)
        inventar = (self.escritor is not None and self.pode_inventar()
                    and random.random() < chance_de_inventar(taxa))
        if self.debug() and self.pode_inventar():
            log(f"[inventar] {taxa:.1f} Hz -> {'frase nova (IA local)' if inventar else 'frase já escrita'}")
        texto = None if inventar else self.engine.escolher_texto(action)
        if not inventar and not texto:
            return None
        plano = {"ctx": ctx, "acao": "bilhete_ia" if inventar else action, "canto": action == "bilhete_canto"}
        escrever = self.escritor(emotion, action) if inventar else None
        if self.fala is None or not self.fala.precisa_preparar(escrever, texto):
            return self.mostrar_bilhete(texto, now, bounds, cursor, plano)
        liberar = lambda *_a: self._liberar(plano)      # noqa: E731
        if not self.fala.preparar(f"post-it ({plano['acao']})", lambda frase: self.entregar(plano, frase),
                                  texto=texto, escrever=escrever, emocao=emotion,
                                  ao_falhar=liberar, ao_cancelar=liberar):
            return None                                 # fila cheia: fica para a próxima
        self.pendente = plano
        return action

    def _imagem(self, action, plan, ctx, emotion, motores, now, bounds, cursor):
        """
        Meme ou foto com fala. A rede decide (INVENTAR) se a IA olha a imagem e comenta, ou se ele usa uma
        reação já escrita. Com a voz natural, a fala é preparada antes e o meme aparece junto com ela.
        """
        thing = plan[1]
        inventar = (self.comentador is not None and self.pode_ver() and getattr(thing, "path", None) is not None
                    and random.random() < chance_de_inventar(motores.get("INVENTAR", 0.0)))
        if self.debug():
            log(f"[inventar] {action}: {'a IA comenta a imagem' if inventar else 'reação já escrita'}")
        texto = None if inventar else self.engine.escolher_reacao(action)
        plano = {"ctx": ctx, "acao": action, "plan": plan, "canto": plan[0] == "corner"}
        escrever = self.comentador(emotion, thing.path) if inventar else None
        if self.fala is None or not self.fala.precisa_preparar(escrever, texto):
            return self._mostrar_imagem(plano, texto, now, bounds, cursor)     # a voz do sistema fala na hora
        liberar = lambda *_a: self._liberar(plano)      # noqa: E731
        sem_fala = lambda *_a: self._sem_fala(plano)    # noqa: E731
        if not self.fala.preparar(f"{action} com fala", lambda frase: self.entregar(plano, frase),
                                  texto=texto, escrever=escrever, emocao=emotion,
                                  ao_falhar=sem_fala, ao_cancelar=liberar):
            return None
        self.pendente = plano
        return action

    def testar_meme(self, emotion, now, bounds, cursor, com_ia=False):
        """
        (Configurações) Traz um meme agora, fora da agenda, para testar: com a voz ligada, com a fala (uma
        reação já escrita, ou a IA comentando, com `com_ia`). Não conta como travessura para a rede aprender.
        Devolve o que aconteceu, para mostrar na tela.
        """
        plan = self.engine.plan("meme", emotion)
        if plan is None:
            return "Não há memes na pasta deste pet."
        nome = Path(plan[1].path).name
        motores = {"INVENTAR": 1e9 if com_ia else 0.0}           # com IA: a rede "quer" inventar
        if self.pode_falar():
            if self._imagem("meme", plan, None, emotion, motores, now, bounds, cursor) is None:
                plan[1].deleteLater()
                return "Não deu para trazer o meme agora (a fila da voz está ocupada?)."
            if self.pendente is None:
                return f"Trouxe {nome}."
            quem = "a IA está olhando a imagem e depois a voz" if com_ia else "a voz"
            return f"Trazendo {nome}: {quem} prepara a fala antes (alguns segundos)."
        plano = {"ctx": None, "acao": "meme", "plan": plan, "canto": plan[0] == "corner"}
        if self._mostrar_imagem(plano, None, now, bounds, cursor) is None:
            return "Não deu para trazer o meme agora (sem lugar na tela)."
        return f"Trouxe {nome}, calado (a voz está desligada)."

    def _sem_fala(self, plano):
        """A IA não comentou a imagem: o meme aparece mesmo assim, com uma reação já escrita."""
        if self.pendente is plano:
            self.entregar(plano, self.engine.escolher_reacao(plano["acao"]))

    def _mostrar_imagem(self, plano, frase, now, bounds, cursor):
        """O meme (ou foto) aparece com a fala: ele leva pela tela, ou aparece num canto."""
        kind, thing = plano["plan"]
        thing.fala = frase
        body = self.behavior.body
        livre = self.behavior.mission is None and body.grounded and not body.held
        if kind == "deliver" and livre:
            self.behavior.start_mission(plano["plan"], bounds, cursor, now)
        elif not self.engine.show_in_corner(thing, bounds, cursor):
            return None
        if plano["ctx"] is not None:                    # o teste das Configurações não ensina a rede
            self.memory.start(plano["ctx"], plano["acao"], thing)
            self.drives.stimulate("mischief")
        return plano["acao"]

    def _liberar(self, plano):
        """A preparação falhou ou foi cancelada: ele pode aprontar outra."""
        if self.pendente is plano:
            self.pendente = None
            if "plan" in plano:
                plano["plan"][1].deleteLater()          # o meme que não vai mais aparecer

    def entregar(self, plano, frase):
        """(Tela) A frase e a fala ficaram prontas: o post-it aparece agora, se ainda puder."""
        if self.pendente is not plano:
            return False
        self.pendente = None
        if not self.pode_entregar(plano["acao"]):
            if self.debug():
                log(f"[preparo] {plano['acao']}: ficou pronto, mas agora não pode aparecer")
            if "plan" in plano:
                plano["plan"][1].deleteLater()          # o meme que não vai aparecer
            return False
        now, bounds, cursor = self.cena()
        if "plan" in plano:
            return self._mostrar_imagem(plano, frase, now, bounds, cursor) is not None
        return self.mostrar_bilhete(frase, now, bounds, cursor, plano) is not None

    def mostrar_bilhete(self, texto, now, bounds, cursor, plano=None, andar=True):
        """
        Mostra o post-it: ele leva até longe do cursor (ou, se estiver ocupado ou `andar` for False,
        aparece num canto). Com `plano`, vira um episódio da memória (contexto e ação). Devolve a ação, ou None.
        """
        thing = self.engine.bilhete(texto, small=bool(plano and plano["canto"]))
        body = self.behavior.body
        if plano is None or not plano["canto"]:
            livre = andar and self.behavior.mission is None and body.grounded and not body.held
            if livre:
                self.behavior.start_mission(("deliver", thing), bounds, cursor, now)
            elif not self.engine.show_in_corner(thing, bounds, cursor):
                return None
        elif not self.engine.show_in_corner(thing, bounds, cursor):
            return None
        acao = plano["acao"] if plano else "avulso"
        if plano is not None:
            self.memory.start(plano["ctx"], acao, thing)
            self.drives.stimulate("mischief")
        return acao

    def on_dismissed(self, thing, elapsed, prof, now):
        """Você dispensou uma travessura: vira frustração e entra na memória como aprendizado."""
        self.senses.dismissed()
        self.drives.touched("dismiss")
        self.memory.on_dismiss(thing, elapsed, prof["dismiss_patience"])
        self.penalty_until = now + PENALTY_SECONDS
        self.dismiss_times.append(now)
        while self.dismiss_times and now - self.dismiss_times[0] > prof["drama_window"]:
            self.dismiss_times.popleft()
        quick = elapsed < QUICK_DISMISS
        if len(self.dismiss_times) >= prof["drama_count"] or (quick and len(self.dismiss_times) >= 2):
            self.emotion.force("dramatico", 4.0, now, PRIORITY["dramatico"])
            self.dismiss_times.clear()

    def clear(self):
        """Tira todas as travessuras da tela e solta o que ele estava carregando."""
        self.behavior.drop_carried()
        self.memory.drop_open_things()
        self.engine.clear()
