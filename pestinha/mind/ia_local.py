"""
IA LOCAL (em teste) - um modelo de linguagem pequeno rodando no computador, com o llama.cpp.

Ele faz duas coisas, e quem decide quando é a rede neural (mind/frases_ia.py monta os pedidos):
    escrever    um post-it sobre o que o pet sente agora (llama-completion)
    ver         olhar um print da tela e escrever um comentário (llama-mtmd-cli: o Qwen3.5 enxerga)

Nada é instalado no sistema nem no Python. O instalador baixa para ia_local/, ao lado do programa:
    llama/      o programa pronto do llama.cpp, publicado pelo próprio projeto (13 a 25 MB, conforme o sistema)
    modelo/     o Qwen3.5-2B compactado (GGUF, 1,3 GB) e a parte dele que enxerga (mmproj, 0,7 GB)
Tudo tem versão fixa e só é usado se a sha256 bater com a anotada aqui.

Cada pedido abre o llama.cpp, que carrega o modelo, responde e fecha: a memória volta na hora.

    python -m pestinha.mind.ia_local                # diz se está instalada
    python -m pestinha.mind.ia_local --instalar     # baixa, confere e testa
    python -m pestinha.mind.ia_local --remover      # apaga ia_local/
"""

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

LLAMA_VERSAO = "b12177"
LLAMA_URL = "https://github.com/ggml-org/llama.cpp/releases/download/{versao}/{arquivo}"
# (sistema, processador) -> (pacote do llama.cpp, sha256). Só o do macOS com Apple Silicon foi testado.
PACOTES = {
    ("darwin", "arm64"): ("llama-b12177-bin-macos-arm64.tar.gz",
                          "618c2cbbe89338501d293488de52143f5d9173d4a63e932a1dc7ea5777d2fcb5"),
    ("darwin", "x86_64"): ("llama-b12177-bin-macos-x64.tar.gz",
                           "ba4ca623cf8819124b0b7667ac465ac557cee5c6070b2065f8348c2d8f6e3bdd"),
    ("win32", "x86_64"): ("llama-b12177-bin-win-cpu-x64.zip",
                          "2d53212b57ccfc50128ec2e704c8ae44fb12df5206a731eef7be63f7669ebc74"),
    ("win32", "arm64"): ("llama-b12177-bin-win-cpu-arm64.zip",
                         "641cf8647fa0f52cddefc967f44f94b3c5d7108782830afc4f5833d4b976f9f8"),
    ("linux", "x86_64"): ("llama-b12177-bin-ubuntu-x64.tar.gz",
                          "5d936162de06187654d1353fe94d65390904f1c67cd1a887023dbc9b0b207284"),
    ("linux", "arm64"): ("llama-b12177-bin-ubuntu-arm64.tar.gz",
                         "2ef14032b3b25f4d10b01b3861b9539756cac4af421919f1b8da56c9a7df4b8f"),
}
MODELO_REPO = "unsloth/Qwen3.5-2B-GGUF"
MODELO_REVISAO = "f6d5376be1edb4d416d56da11e5397a961aca8ae"
MODELO_ARQUIVO = "Qwen3.5-2B-Q4_K_M.gguf"
MODELO_SHA256 = "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"
MODELO_BYTES = 1280835840
MODELO_URL = f"https://huggingface.co/{MODELO_REPO}/resolve/{MODELO_REVISAO}/{MODELO_ARQUIVO}"
# a parte do modelo que lê imagens (projetor multimodal), do mesmo repositório e da mesma revisão
VISAO_ARQUIVO = "mmproj-F16.gguf"
VISAO_SHA256 = "7035e9cb8d7c6a9681d07eef9a364783e86ea4cd73faab2eabb4f43a101830c7"
VISAO_BYTES = 668227264
VISAO_URL = f"https://huggingface.co/{MODELO_REPO}/resolve/{MODELO_REVISAO}/{VISAO_ARQUIVO}"

PROGRAMA = "llama-completion"         # gera uma vez e termina (o llama-cli é o de conversa)
PROGRAMA_VISAO = "llama-mtmd-cli"     # o mesmo, com imagem
IMAGEM_TOKENS = 256                   # no máximo isso por imagem: o print vira menos tokens e sai mais rápido
# A conversa no formato do Qwen com o pensamento vazio, para o llama-mtmd-cli (que aplica o modelo de
# conversa sozinho). O dele, que vem no modelo, deixa o Qwen3.5 pensar em inglês antes de responder.
TEMPLATE_SEM_PENSAR = (
    "{%- for message in messages -%}<|im_start|>{{ message.role }}\n{{ message.content }}<|im_end|>\n"
    "{% endfor -%}{%- if add_generation_prompt -%}<|im_start|>assistant\n<think>\n\n</think>\n\n{% endif -%}"
)
TEMPO_MAXIMO_S = 60.0                 # s: passou disso, a geração é cancelada
CONTEXTO = 2048                       # tokens: o pedido é curto, e contexto pequeno carrega mais rápido
AGENTE = "Pestinha (instalador da IA local)"


def gb(valor):
    """1.28 -> '1,3 GB'."""
    return f"{valor:.1f}".replace(".", ",") + " GB"


# ---------------- onde estão as coisas ----------------

def pacote(sistema=None, maquina=None):
    """(arquivo, sha256) do llama.cpp para este computador, ou None se não houver pacote pronto."""
    sistema = sistema or sys.platform
    maquina = (maquina or platform.machine()).lower()
    maquina = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(maquina, maquina)
    return PACOTES.get((sistema, maquina))


def programa(pasta, nome=PROGRAMA):
    """Um programa do llama.cpp dentro de ia_local/llama/ (o pacote de cada sistema arruma as pastas de um jeito)."""
    base = Path(pasta) / "llama"
    if not base.is_dir():
        return None
    for nome in (nome, nome + ".exe"):
        for achado in sorted(base.rglob(nome)):
            if achado.is_file():
                return achado
    return None


def modelo(pasta):
    """O arquivo do modelo (GGUF)."""
    return Path(pasta) / "modelo" / MODELO_ARQUIVO


def visao(pasta):
    """O arquivo da parte do modelo que enxerga (mmproj)."""
    return Path(pasta) / "modelo" / VISAO_ARQUIVO


def instalada(pasta):
    """Instalada e completa (o instalador grava instalado.json só depois do teste)."""
    pasta = Path(pasta)
    return (pasta / "instalado.json").exists() and programa(pasta) is not None and modelo(pasta).exists()


def visao_instalada(pasta):
    """Instalada e enxergando: o modelo, a parte da visão e o programa que lê imagens."""
    return instalada(pasta) and visao(pasta).exists() and programa(pasta, PROGRAMA_VISAO) is not None


# ---------------- gerar ----------------

def chatml(sistema, pedido):
    """
    A conversa no formato do Qwen (ChatML), já com o bloco de pensamento vazio: é assim que o modo
    "sem pensar" do Qwen3.5 funciona por dentro, e o modelo responde direto. Montamos à mão porque o
    modo de conversa do llama-completion desta versão quebra com o modelo de conversa do Qwen3.5.
    """
    return (f"<|im_start|>system\n{sistema}<|im_end|>\n"
            f"<|im_start|>user\n{pedido}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def comando(pasta, prompt, tokens=40, temperatura=0.8, seed=-1, programa_=None):
    """A linha de comando de uma geração: carrega o modelo, continua o `prompt` e termina."""
    exe = list(programa_) if isinstance(programa_, (list, tuple)) else [str(programa_ or programa(pasta))]
    return exe + [
        "-m", str(modelo(pasta)),
        "-p", prompt,
        "-no-cnv", "--no-escape",         # texto puro, do jeito que veio
        "-n", str(tokens),
        "-c", str(CONTEXTO),
        "--temp", str(temperatura),
        "-s", str(seed),
        "--no-display-prompt", "--simple-io", "--no-perf", "-lv", "0",
        "--offline",                      # nunca tenta a internet
    ]


def comando_visao(pasta, sistema, pedido, imagem, tokens=40, temperatura=0.7, seed=-1, programa_=None):
    """A linha de comando de uma olhada: carrega o modelo e a visão, lê a `imagem`, responde e termina."""
    exe = list(programa_) if isinstance(programa_, (list, tuple)) else [
        str(programa_ or programa(pasta, PROGRAMA_VISAO))]
    return exe + [
        "-m", str(modelo(pasta)),
        "--mmproj", str(visao(pasta)),
        "--image", str(imagem),
        "--image-max-tokens", str(IMAGEM_TOKENS),
        "--jinja", "--chat-template", TEMPLATE_SEM_PENSAR,
        "-sys", sistema,
        "-p", pedido,
        "-n", str(tokens),
        "-c", str(CONTEXTO),
        "--temp", str(temperatura),
        "-s", str(seed),
        "-lv", "0",
        "--offline",
    ]


def resposta(saida):
    """O texto que o modelo escreveu, sem as marcas do llama.cpp e do Qwen."""
    texto = saida.decode("utf-8", errors="replace") if isinstance(saida, bytes) else str(saida)
    for marca in ("[end of text]", "<|im_end|>", "<|endoftext|>"):
        texto = texto.replace(marca, "")
    if "</think>" in texto:
        texto = texto.split("</think>", 1)[1]
    elif "<think>" in texto:
        texto = ""                                    # começou a pensar e não terminou: não serve
    return texto.strip()


def rodar_simples(cmd, entrada=None, tempo=TEMPO_MAXIMO_S, erros=subprocess.PIPE, ambiente=None):
    """Roda e espera (quem roda pelo mind/preparo.py usa o dele, que dá para cancelar)."""
    try:
        return subprocess.run(cmd, input=entrada, stdin=None if entrada is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=erros, timeout=tempo, env=ambiente, check=False)
    except subprocess.TimeoutExpired as erro:
        raise RuntimeError(f"passou de {tempo:.0f} s") from erro


def _executar(cmd, tempo, rodar):
    """Roda o llama.cpp e devolve a resposta limpa. Levanta RuntimeError se não der."""
    try:
        r = (rodar or rodar_simples)(cmd, tempo=tempo)
    except OSError as erro:
        raise RuntimeError(f"não abriu o llama.cpp: {erro}") from erro
    if r.returncode != 0:
        erro = (r.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()[-1:] or ["?"]
        raise RuntimeError(f"o llama.cpp saiu com o código {r.returncode}: {erro[0][:200]}")
    return resposta(r.stdout)


def gerar(pasta, prompt, tempo=TEMPO_MAXIMO_S, rodar=None, **kw):
    """Gera e devolve a resposta (veja `resposta`). Levanta RuntimeError se não der."""
    return _executar(comando(pasta, prompt, **kw), tempo, rodar)


def ver(pasta, sistema, pedido, imagem, tempo=TEMPO_MAXIMO_S, rodar=None, **kw):
    """Olha a imagem e devolve o que o modelo escreveu. Levanta RuntimeError se não der."""
    return _executar(comando_visao(pasta, sistema, pedido, imagem, **kw), tempo, rodar)


# ---------------- instalar ----------------

def sha256_de(caminho):
    """sha256 de um arquivo (lido aos pedaços)."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url, destino, sha256, escrever=print, total=None):
    """
    Baixa `url` para `destino` e confere a sha256. Se a internet cair, a próxima tentativa continua do
    pedaço já baixado (destino.parte). Levanta RuntimeError se o arquivo não bater.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parte = destino.with_name(destino.name + ".parte")
    ja = parte.stat().st_size if parte.exists() else 0
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    if ja and url.startswith("http"):
        pedido.add_header("Range", f"bytes={ja}-")
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        continua = getattr(resposta, "status", 200) == 206
        modo = "ab" if continua else "wb"
        feito = ja if continua else 0
        ultimo = time.monotonic()
        with open(parte, modo) as f:
            for bloco in iter(lambda: resposta.read(1024 * 1024), b""):
                f.write(bloco)
                feito += len(bloco)
                if total and time.monotonic() - ultimo > 3:
                    escrever(f"    baixando... {gb(feito / 1e9)} de {gb(total / 1e9)}")
                    ultimo = time.monotonic()
    if sha256_de(parte) != sha256:
        parte.unlink()
        raise RuntimeError(f"{destino.name} veio diferente do esperado (sha256 não bate); apaguei, tente de novo")
    parte.replace(destino)
    return destino


def extrair(arquivo, destino):
    """Abre o .tar.gz ou .zip do llama.cpp em `destino` (sem deixar nada escapar da pasta)."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    if str(arquivo).endswith(".zip"):
        with zipfile.ZipFile(arquivo) as z:
            z.extractall(destino)                       # o zipfile já recusa caminhos absolutos e ".."
        return
    with tarfile.open(arquivo, "r:gz") as t:
        try:
            t.extractall(destino, filter="data")        # recusa caminhos e links que saem da pasta
        except TypeError:                               # Python 3.11.0 a 3.11.3: confere à mão
            raiz = destino.resolve()
            for membro in t.getmembers():
                alvo = (destino / membro.name).resolve()
                if raiz not in alvo.parents and alvo != raiz:
                    raise RuntimeError(f"arquivo suspeito no pacote: {membro.name}")
            t.extractall(destino)


def teste(pasta, gerar_=gerar):
    """Gera uma resposta curtinha. Devolve (ok, segundos, texto)."""
    inicio = time.monotonic()
    try:
        texto = gerar_(pasta, chatml("Responda com uma palavra.", "Diga oi."), tokens=8, temperatura=0.0, seed=1)
    except RuntimeError as erro:
        return False, time.monotonic() - inicio, str(erro)
    return bool(texto.strip()), time.monotonic() - inicio, texto.strip()


def instalar(pasta, escrever=print, baixar_=baixar, teste_=teste, sistema=None, maquina=None):
    """Baixa o llama.cpp e o modelo para `pasta` (pulando o que já está pronto) e testa. Devolve True se deu."""
    pasta = Path(pasta)
    escolhido = pacote(sistema, maquina)
    if escolhido is None:
        escrever(f"O llama.cpp não tem programa pronto para este computador ({sys.platform}, {platform.machine()}).")
        return False
    arquivo, sha = escolhido
    inicio = time.monotonic()
    try:
        escrever(f"[1/4] llama.cpp {LLAMA_VERSAO} ({arquivo})")
        if programa(pasta) is not None and programa(pasta, PROGRAMA_VISAO) is not None:
            escrever("    já está aqui")
        else:
            baixado = baixar_(LLAMA_URL.format(versao=LLAMA_VERSAO, arquivo=arquivo),
                              pasta / "downloads" / arquivo, sha, escrever)
            shutil.rmtree(pasta / "llama", ignore_errors=True)
            extrair(baixado, pasta / "llama")
            baixado.unlink()
            for nome in (PROGRAMA, PROGRAMA_VISAO):
                if programa(pasta, nome) is None:
                    raise RuntimeError(f"o pacote não trouxe o {nome}")
        escrever(f"[2/4] Modelo {MODELO_ARQUIVO} (uns {gb(MODELO_BYTES / 1e9)}, do Hugging Face)")
        if modelo(pasta).exists() and modelo(pasta).stat().st_size == MODELO_BYTES:
            escrever("    já está aqui")
        else:
            baixar_(MODELO_URL, modelo(pasta), MODELO_SHA256, escrever, MODELO_BYTES)
        escrever(f"[3/4] Visão: {VISAO_ARQUIVO} (uns {gb(VISAO_BYTES / 1e9)}, a parte do modelo que enxerga)")
        if visao(pasta).exists() and visao(pasta).stat().st_size == VISAO_BYTES:
            escrever("    já está aqui")
        else:
            baixar_(VISAO_URL, visao(pasta), VISAO_SHA256, escrever, VISAO_BYTES)
        escrever("[4/4] Teste: carregando o modelo e gerando uma resposta")
        ok, segundos, texto = teste_(pasta)
        if not ok:
            raise RuntimeError(f"o teste não respondeu: {texto}")
        escrever(f"    respondeu {texto!r} em {segundos:.1f} s")
    except (OSError, RuntimeError, tarfile.TarError, zipfile.BadZipFile) as erro:
        escrever(f"Não terminou: {erro}")
        escrever("Pode rodar de novo: ele continua de onde parou.")
        return False
    (pasta / "instalado.json").write_text(json.dumps({
        "llama": LLAMA_VERSAO, "pacote": arquivo, "modelo": f"{MODELO_REPO}/{MODELO_ARQUIVO}",
        "visao": VISAO_ARQUIVO, "revisao": MODELO_REVISAO, "teste_s": round(segundos, 1),
        "instalado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=1), encoding="utf-8")
    escrever(f"Pronto! A IA local está instalada em {pasta} ({(time.monotonic() - inicio) / 60:.1f} min).")
    return True


def remover(pasta):
    """Apaga a IA local inteira."""
    shutil.rmtree(pasta, ignore_errors=True)


def main(argv=None):
    """Linha de comando: diz se está instalada; --instalar baixa; --remover apaga."""
    from ..paths import Paths
    argv = sys.argv[1:] if argv is None else argv
    pasta = Path(argv[argv.index("--pasta") + 1]) if "--pasta" in argv[:-1] else Paths().ia_local
    if "--remover" in argv:
        remover(pasta)
        print(f"Removida: {pasta}")
        return 0
    if "--instalar" in argv:
        return 0 if instalar(pasta) else 1
    estado = "instalada, com visão" if visao_instalada(pasta) else "instalada" if instalada(pasta) else "não instalada"
    print(f"IA local {estado} em {pasta}")
    print("Para instalar: python -m pestinha.mind.ia_local --instalar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
