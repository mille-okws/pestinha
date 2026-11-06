"""
INSTALAÇÃO DA VOZ NATURAL - diz se este computador aguenta o OmniVoice e, se aguentar, instala.

    analisar(pasta)     lista do que foi conferido: (nome, "ok" | "aviso" | "falha", explicação)
    compativel(itens)   nenhuma falha
    instalar(pasta)     cria voz_natural/ambiente, instala torch + OmniVoice, baixa o modelo em
                        voz_natural/modelo, testa e grava voz_natural/instalado.json
    remover(pasta)      apaga voz_natural/ inteira

Cada passo pula o que já está pronto: se a internet cair no meio, rodar de novo continua de onde parou.
Pela linha de comando (na pasta do Pestinha):
    python -m pestinha.mind.voz_instalacao              só analisa
    python -m pestinha.mind.voz_instalacao --instalar   analisa e instala
    python -m pestinha.mind.voz_instalacao --remover    apaga a voz natural
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .voz_motor import TRABALHADOR, instalada, python_do_ambiente

PACOTES = ["torch==2.8.0", "torchaudio==2.8.0", "omnivoice==0.2.1", "soundfile"]
MODELO_REPO = "k2-fsa/OmniVoice"
MODELO_REVISAO = "c5fdb5ccb189668d56333f77ba2629f4cd7535f4"     # a versão testada com o Pestinha
MODELO_GB = 3.3
AMBIENTE_GB = 1.2
LIVRE_MINIMO_GB = 6.0
MEMORIA_MINIMA_GB = 8
MEMORIA_BOA_GB = 16
MACOS_MINIMO = (13, 0)
PYTHON_ACEITOS = ((3, 9), (3, 13))


def gb(valor):
    """4.5 -> '4,5 GB' (com vírgula, como se escreve em português)."""
    return f"{valor:.1f}".replace(".", ",") + " GB"


# ---------------- análise ----------------

def _sysctl(nome):
    """Valor de um sysctl do macOS (texto), ou None."""
    try:
        saida = subprocess.run(["sysctl", "-n", nome], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return saida.stdout.strip() if saida.returncode == 0 else None


def _livre_gb(pasta):
    """Espaço livre (GB) no disco da pasta (ou da primeira pasta-mãe que existir)."""
    pasta = Path(pasta).resolve()
    while not pasta.exists() and pasta.parent != pasta:
        pasta = pasta.parent
    return shutil.disk_usage(pasta).free / 1024 ** 3


def coletar_fatos(pasta):
    """O que a análise precisa saber deste computador."""
    memoria = _sysctl("hw.memsize") if sys.platform == "darwin" else None
    return {
        "sistema": sys.platform,
        "maquina": platform.machine(),
        "mac_arm64": _sysctl("hw.optional.arm64") == "1" if sys.platform == "darwin" else False,
        "macos": platform.mac_ver()[0] if sys.platform == "darwin" else "",
        "memoria_gb": int(memoria) / 1024 ** 3 if memoria and memoria.isdigit() else None,
        "livre_gb": _livre_gb(pasta),
        "python": tuple(sys.version_info[:2]),
        "congelado": bool(getattr(sys, "frozen", False)),
        "instalada": instalada(pasta),
    }


def _versao(texto):
    """'14.6.1' -> (14, 6)."""
    partes = [int(p) for p in str(texto).split(".")[:2] if p.isdigit()]
    return tuple(partes + [0] * (2 - len(partes)))


def analisar(pasta=None, fatos=None):
    """Confere o computador. Devolve [(nome, estado, explicação)] na ordem em que aparecem na tela."""
    f = fatos if fatos is not None else coletar_fatos(pasta)
    itens = []
    if f["sistema"] != "darwin":
        itens.append(("Sistema", "falha", "Por enquanto a voz natural só funciona no macOS."))
        return itens
    itens.append(("Sistema", "ok", f"macOS {f['macos'] or '(versão desconhecida)'}"))
    if f["macos"] and _versao(f["macos"]) < MACOS_MINIMO:
        itens.append(("Versão do macOS", "falha", f"Precisa do macOS {MACOS_MINIMO[0]} ou mais novo."))
    if f["maquina"] == "arm64":
        itens.append(("Processador", "ok", "Apple Silicon (M1 ou mais novo): o modelo roda na GPU do Mac."))
    elif f["mac_arm64"]:
        itens.append(("Processador", "falha", "O Mac é Apple Silicon, mas este Python é da versão Intel "
                      "(roda pelo Rosetta). Instale um Python para Apple Silicon (arm64) e abra o Pestinha com ele."))
    else:
        itens.append(("Processador", "falha", "Mac com processador Intel: o PyTorch atual não tem versão para ele."))
    memoria = f["memoria_gb"]
    if memoria is None:
        itens.append(("Memória", "aviso", "Não deu para ler a memória (RAM). O modelo usa uns 3 GB."))
    elif memoria < MEMORIA_MINIMA_GB:
        itens.append(("Memória", "falha", f"{memoria:.0f} GB de RAM. Precisa de pelo menos {MEMORIA_MINIMA_GB} GB."))
    elif memoria < MEMORIA_BOA_GB:
        itens.append(("Memória", "aviso", f"{memoria:.0f} GB de RAM: funciona, mas o computador pode ficar "
                      "mais lento enquanto ele gera uma fala."))
    else:
        itens.append(("Memória", "ok", f"{memoria:.0f} GB de RAM."))
    if f["instalada"]:
        itens.append(("Espaço em disco", "ok", "A voz natural já está instalada."))
    elif f["livre_gb"] < LIVRE_MINIMO_GB:
        itens.append(("Espaço em disco", "falha", f"{gb(f['livre_gb'])} livres. Precisa de {LIVRE_MINIMO_GB:.0f} GB "
                      f"(baixa uns {gb(AMBIENTE_GB + MODELO_GB)})."))
    else:
        itens.append(("Espaço em disco", "ok", f"{f['livre_gb']:.0f} GB livres (baixa uns {gb(AMBIENTE_GB + MODELO_GB)})."))
    if f["congelado"]:
        itens.append(("Python", "falha", "O executável do Pestinha não traz o Python. Para usar a voz natural, "
                      "rode o Pestinha pelo código-fonte (python main.py)."))
    elif not (PYTHON_ACEITOS[0] <= f["python"] <= PYTHON_ACEITOS[1]):
        itens.append(("Python", "falha", f"Python {f['python'][0]}.{f['python'][1]}: o PyTorch precisa de "
                      f"{PYTHON_ACEITOS[0][0]}.{PYTHON_ACEITOS[0][1]} a {PYTHON_ACEITOS[1][0]}.{PYTHON_ACEITOS[1][1]}."))
    else:
        itens.append(("Python", "ok", f"Python {f['python'][0]}.{f['python'][1]}."))
    return itens


def compativel(itens):
    """Nenhum item com falha."""
    return all(estado != "falha" for _nome, estado, _explicacao in itens)


# ---------------- instalação ----------------

def _rodar(comando, escrever, ambiente=None):
    """Roda um comando mostrando a saída linha a linha. Devolve o código de saída."""
    try:
        processo = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", env=ambiente)
    except OSError as erro:
        escrever(f"não deu para rodar {comando[0]}: {erro}")
        return 1
    for linha in processo.stdout:
        linha = linha.rstrip()
        if linha:
            escrever("    " + linha)
    return processo.wait()


def _tamanho_gb(pasta):
    """Quanto a pasta ocupa (GB)."""
    return sum(p.stat().st_size for p in Path(pasta).rglob("*") if p.is_file()) / 1024 ** 3


def _modelo_completo(modelo):
    """Os dois arquivos grandes do modelo estão lá."""
    modelo = Path(modelo)
    return all((modelo / nome).exists() and (modelo / nome).stat().st_size > 100 * 1024 ** 2
               for nome in ("model.safetensors", "audio_tokenizer/model.safetensors"))


def instalar(pasta, escrever=print, rodar=None, python_base=None):
    """Instala a voz natural em `pasta` (voz_natural/). Devolve True se terminou e o teste passou."""
    rodar = rodar or _rodar
    pasta = Path(pasta)
    python = python_do_ambiente(pasta)
    modelo = pasta / "modelo"
    sem_rede = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONIOENCODING="utf-8")

    escrever("[1/4] Ambiente Python separado (voz_natural/ambiente)")
    if python.exists():
        escrever("    já existe")
    elif rodar([python_base or sys.executable, "-m", "venv", str(pasta / "ambiente")], escrever) != 0:
        escrever("ERRO: não deu para criar o ambiente Python.")
        return False

    escrever(f"[2/4] Bibliotecas: PyTorch e OmniVoice (uns {gb(AMBIENTE_GB)})")
    if rodar([str(python), "-c", "import torch, omnivoice, soundfile"], lambda _l: None, sem_rede) == 0:
        escrever("    já instaladas")
    else:
        rodar([str(python), "-m", "pip", "install", "--upgrade", "pip", "--progress-bar", "off", "-q"], escrever)
        if rodar([str(python), "-m", "pip", "install", "--progress-bar", "off", *PACOTES], escrever) != 0:
            escrever("ERRO: a instalação das bibliotecas falhou. Confira a internet e tente de novo.")
            return False

    escrever(f"[3/4] Modelo OmniVoice (uns {gb(MODELO_GB)}, do Hugging Face)")
    if _modelo_completo(modelo):
        escrever("    já baixado")
    else:
        parar = threading.Event()

        def progresso():
            while not parar.wait(3.0):
                if modelo.exists():
                    escrever(f"    baixando... {gb(_tamanho_gb(modelo))} de {gb(MODELO_GB)}")

        threading.Thread(target=progresso, daemon=True).start()
        codigo = rodar([str(python), "-c",
                        "from huggingface_hub import snapshot_download; "
                        f"snapshot_download({MODELO_REPO!r}, revision={MODELO_REVISAO!r}, local_dir={str(modelo)!r})"],
                       escrever, dict(os.environ, HF_HUB_DISABLE_PROGRESS_BARS="1"))
        parar.set()
        if codigo != 0 or not _modelo_completo(modelo):
            escrever("ERRO: o download do modelo não terminou. Confira a internet e tente de novo "
                     "(ele continua de onde parou).")
            return False

    escrever("[4/4] Teste: gerando uma frase")
    respostas = []

    def guardar(linha):
        respostas.append(linha)
        escrever(linha)

    rodar([str(python), "-u", str(TRABALHADOR), "--modelo", str(modelo), "--teste"],
          lambda linha: guardar(linha.strip()), sem_rede)
    resultado = next((json.loads(r) for r in reversed(respostas) if r.startswith("{")), {})
    if not resultado.get("ok"):
        escrever("ERRO: o modelo não conseguiu gerar a frase de teste. Veja as mensagens acima.")
        return False
    (pasta / "instalado.json").write_text(json.dumps({
        "pacotes": PACOTES, "modelo": MODELO_REPO, "revisao": MODELO_REVISAO,
        "dispositivo": resultado.get("dispositivo"), "instalado_em": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    escrever(f"Pronto! A voz natural está instalada (roda em: {resultado.get('dispositivo')}).")
    return True


def remover(pasta):
    """Apaga a voz natural (o ambiente, o modelo e a marca de instalada)."""
    pasta = Path(pasta)
    if pasta.exists():
        shutil.rmtree(pasta)


# ---------------- linha de comando ----------------

SIMBOLO = {"ok": "✔", "aviso": "!", "falha": "✖"}


def main(argv=None):
    """Analisa este computador e, com --instalar, instala; com --remover, apaga."""
    from ..paths import Paths
    argv = sys.argv[1:] if argv is None else argv
    pasta = Path(argv[argv.index("--pasta") + 1]) if "--pasta" in argv[:-1] else Paths().voz_natural
    if "--remover" in argv:
        remover(pasta)
        print(f"Voz natural removida ({pasta}).")
        return 0
    itens = analisar(pasta)
    print("Este computador e a voz natural (OmniVoice):")
    for nome, estado, explicacao in itens:
        print(f"  {SIMBOLO[estado]} {nome}: {explicacao}")
    if not compativel(itens):
        print("Não dá para instalar a voz natural aqui. O Pestinha continua usando a voz do sistema.")
        return 1
    if "--instalar" not in argv:
        print("Compatível. Para instalar: python -m pestinha.mind.voz_instalacao --instalar")
        return 0
    inicio = time.monotonic()
    ok = instalar(pasta, lambda linha: print(linha, flush=True))
    print(f"({(time.monotonic() - inicio) / 60:.1f} min)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
