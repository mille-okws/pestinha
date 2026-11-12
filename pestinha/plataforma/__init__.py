"""
PLATAFORMA - a única parte do código que conhece o sistema operacional.

Cada sistema tem um módulo com as mesmas funções (windows.py, macos.py, linux.py). Este arquivo
escolhe o certo na importação. Os retângulos são em pixels físicos (o app divide pelo dpr).

    ocioso_segundos()            segundos desde o último teclado ou mouse
    processo_ativo()             nome (minúsculo) do programa em primeiro plano
    retangulo_ativo(escala)      retângulo da janela em primeiro plano, ou None
    tela_cheia()                 a janela em primeiro plano cobre o monitor inteiro
    janelas_visiveis(excluir, escala)   [(id, (l, t, r, b), maximizada)] de cima para baixo
    sem_foco_nativo(janela_id)   a janela do pet não rouba o foco (quando o sistema permite); no macOS, fica na frente de tudo
    janela_normal(janela_id)     um painel (monitor, protesto) que não rouba o foco, mas fica no nível normal:
                                 outros programas podem ficar por cima dele
    trazer_para_frente(janela_id)   põe a janela na frente das outras (abrir um painel pelo menu)
    iniciar_atalho(callback)     Ctrl+Alt+Shift+B; devolve True se registrou
    cursor()                     (x, y) do cursor visto pelo sistema, ou None para usar o do Qt (só o kwin)

Só no macOS, por enquanto (TEM_VOZ diz se existe; sem ela, as duas não fazem nada e devolvem None):
    falar(texto, voz)            lê o texto com a voz do sistema, sem esperar; devolve o processo
    tocar_audio(caminho)         toca um WAV, sem esperar; devolve o processo

Print da tela (para o pet comentar o que você está fazendo; só com a permissão "Espiar a tela"):
    capturar_tela(destino)       salva um PNG do monitor principal; True se deu. No macOS roda em
                                 qualquer thread (CAPTURA_EM_QUALQUER_THREAD); nos outros, só na da tela
    permissao_tela()             o sistema já deixa (macOS: Gravação de Tela); não pergunta nada
    pedir_permissao_tela()       abre a pergunta do sistema (macOS); nos outros não precisa

Só no Windows, por enquanto (TEM_INICIO_AUTOMATICO diz se existe):
    inicia_com_sistema()         o programa está marcado para abrir ao entrar no sistema
    definir_inicio_com_sistema(ligado)   liga ou desliga isso; devolve True se conseguiu
"""

import os
import sys

from . import _comum

if sys.platform == "win32":
    from . import windows as _backend
elif sys.platform == "darwin":
    from . import macos as _backend
elif os.environ.get("XDG_SESSION_TYPE") == "wayland" and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", ""):
    from . import kwin as _backend
else:
    from . import linux as _backend

NOME_DO_SISTEMA = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")

ocioso_segundos = _backend.ocioso_segundos
processo_ativo = _backend.processo_ativo
retangulo_ativo = _backend.retangulo_ativo
tela_cheia = _backend.tela_cheia
janelas_visiveis = _backend.janelas_visiveis
sem_foco_nativo = _backend.sem_foco_nativo
janela_normal = getattr(_backend, "janela_normal", _backend.sem_foco_nativo)    # nos outros, o Qt já resolve
trazer_para_frente = getattr(_backend, "trazer_para_frente", lambda janela_id: None)
iniciar_atalho = _backend.iniciar_atalho
cursor = getattr(_backend, "cursor", lambda: None)

TEM_VOZ = hasattr(_backend, "falar")
falar = getattr(_backend, "falar", lambda texto, voz=None: None)
tocar_audio = getattr(_backend, "tocar_audio", lambda caminho: None)

capturar_tela = getattr(_backend, "capturar_tela", _comum.capturar_tela_qt)
CAPTURA_EM_QUALQUER_THREAD = hasattr(_backend, "capturar_tela")
permissao_tela = getattr(_backend, "permissao_tela", lambda: True)
pedir_permissao_tela = getattr(_backend, "pedir_permissao_tela", lambda: True)

TEM_INICIO_AUTOMATICO = hasattr(_backend, "definir_inicio_com_sistema")
inicia_com_sistema = getattr(_backend, "inicia_com_sistema", lambda: False)
definir_inicio_com_sistema = getattr(_backend, "definir_inicio_com_sistema", lambda ligado: False)
