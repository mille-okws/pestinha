"""
IA local (em teste): instalação do llama.cpp, do modelo e da visão, o pedido que sai do estado da rede,
a limpeza da resposta, escrever e comentar a tela, e o post-it que ele entrega.

Nada aqui baixa nem roda o modelo de verdade: o "llama.cpp" é um script Python que responde o que o
teste manda. O teste com o modelo real é o passo [4/4] do instalador.
"""
import io
import json
import os
import sys
import tarfile
import textwrap
import time
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pestinha import config  # noqa: E402
from pestinha.mind import frases_ia, ia_local  # noqa: E402
from pestinha.paths import Paths  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


# ---------------- llama.cpp falso ----------------

def llama_falso(tmp_path, respostas, codigo=0):
    """Um 'llama-completion' que devolve as `respostas` em ordem (a última se repete) e anota cada chamada."""
    script = tmp_path / "llama_falso.py"
    estado = tmp_path / "chamadas.txt"
    script.write_text(textwrap.dedent(f"""
        import sys
        from pathlib import Path
        estado = Path({str(estado)!r})
        n = len(estado.read_text(encoding="utf-8").splitlines()) if estado.exists() else 0
        with open(estado, "a", encoding="utf-8") as f:
            f.write(" ".join(sys.argv[1:]).replace("\\n", "\\\\n") + "\\n")
        respostas = {respostas!r}
        sys.stdout.buffer.write(respostas[min(n, len(respostas) - 1)].encode("utf-8"))  # como o llama.cpp
        sys.exit({codigo})
    """), encoding="utf-8")
    return [sys.executable, str(script)], estado


def resposta_qwen(texto):
    """Como o llama.cpp devolve: o bloco de pensamento vazio, o texto e a marca de fim."""
    return f"<think>\n\n</think>\n\n{texto} [end of text]\n"


def _instalada_falsa(pasta, visao=True):
    """Uma ia_local/ com tudo no lugar (programas e modelo vazios); `visao` põe a parte que enxerga."""
    for nome in (ia_local.PROGRAMA, ia_local.PROGRAMA_VISAO):
        exe = pasta / "llama" / "llama-b1" / nome
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("")
    ia_local.modelo(pasta).parent.mkdir(parents=True)
    ia_local.modelo(pasta).write_text("")
    if visao:
        ia_local.visao(pasta).write_text("")
    (pasta / "instalado.json").write_text("{}")


def _usar_llama_falso(monkeypatch, prog):
    """Os comandos de texto e de visão passam a abrir o llama falso (funciona em qualquer sistema)."""
    texto, visao = ia_local.comando, ia_local.comando_visao
    monkeypatch.setattr(ia_local, "comando", lambda pasta, prompt, **kw: texto(pasta, prompt, programa_=prog, **kw))
    monkeypatch.setattr(ia_local, "comando_visao",
                        lambda pasta, *a, **kw: visao(pasta, *a, programa_=prog, **kw))


# ---------------- onde estão as coisas ----------------

@pytest.mark.parametrize("sistema, maquina, esperado", [
    ("darwin", "arm64", "macos-arm64"),
    ("darwin", "x86_64", "macos-x64"),
    ("win32", "AMD64", "win-cpu-x64"),
    ("win32", "ARM64", "win-cpu-arm64"),
    ("linux", "x86_64", "ubuntu-x64"),
    ("linux", "aarch64", "ubuntu-arm64"),
])
def test_cada_sistema_tem_o_seu_llama_cpp(sistema, maquina, esperado):
    arquivo, sha = ia_local.pacote(sistema, maquina)
    assert esperado in arquivo and ia_local.LLAMA_VERSAO in arquivo
    assert len(sha) == 64 and int(sha, 16) >= 0


def test_sistema_sem_pacote_pronto():
    assert ia_local.pacote("freebsd", "amd64") is None
    assert ia_local.pacote("linux", "riscv64") is None


def test_versoes_fixas_e_conferidas():
    assert all(ia_local.LLAMA_VERSAO in arq and len(sha) == 64 for arq, sha in ia_local.PACOTES.values())
    assert ia_local.MODELO_REVISAO in ia_local.MODELO_URL and ia_local.MODELO_ARQUIVO in ia_local.MODELO_URL
    assert len(ia_local.MODELO_SHA256) == 64 and ia_local.MODELO_BYTES > 10 ** 9
    # a visão vem do mesmo repositório, na mesma revisão do modelo
    assert ia_local.MODELO_REVISAO in ia_local.VISAO_URL and ia_local.VISAO_ARQUIVO in ia_local.VISAO_URL
    assert len(ia_local.VISAO_SHA256) == 64 and ia_local.VISAO_BYTES > 10 ** 8


def test_acha_o_programa_onde_o_pacote_puser(tmp_path):
    assert ia_local.programa(tmp_path) is None
    exe = tmp_path / "llama" / "build" / "bin" / (ia_local.PROGRAMA + ".exe")
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert ia_local.programa(tmp_path) == exe


def test_instalada_precisa_de_tudo(tmp_path):
    assert not ia_local.instalada(tmp_path)
    _instalada_falsa(tmp_path)
    assert ia_local.instalada(tmp_path) and ia_local.visao_instalada(tmp_path)
    ia_local.visao(tmp_path).unlink()                      # instalada antes da visão existir
    assert ia_local.instalada(tmp_path) and not ia_local.visao_instalada(tmp_path)
    (tmp_path / "instalado.json").unlink()                 # o instalador não terminou
    assert not ia_local.instalada(tmp_path)


def test_ia_local_fica_fora_dos_seus_dados(tmp_path):
    paths = Paths(root=tmp_path)
    assert paths.ia_local == tmp_path / "ia_local"
    assert paths.memory not in paths.ia_local.parents     # "apagar todos os dados" não apaga o download


# ---------------- gerar ----------------

def test_conversa_no_formato_do_qwen_sem_pensar():
    p = ia_local.chatml("seja breve", "oi")
    assert p.startswith("<|im_start|>system\nseja breve<|im_end|>\n<|im_start|>user\noi<|im_end|>\n")
    assert p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")      # pensamento vazio: responde direto


def test_comando_carrega_o_modelo_gera_e_sai_sem_internet(tmp_path):
    _instalada_falsa(tmp_path)
    cmd = ia_local.comando(tmp_path, "PROMPT", tokens=12, temperatura=0.5, seed=7)
    assert cmd[0] == str(ia_local.programa(tmp_path))
    assert cmd[cmd.index("-m") + 1] == str(ia_local.modelo(tmp_path)) and cmd[cmd.index("-p") + 1] == "PROMPT"
    assert "-no-cnv" in cmd and "--offline" in cmd and "--no-display-prompt" in cmd
    assert cmd[cmd.index("-n") + 1] == "12" and cmd[cmd.index("-s") + 1] == "7"


def test_comando_de_visao_le_a_imagem_sem_pensar_e_sem_internet(tmp_path):
    _instalada_falsa(tmp_path)
    cmd = ia_local.comando_visao(tmp_path, "SISTEMA", "PEDIDO", tmp_path / "tela.png", tokens=12, seed=7)
    assert cmd[0] == str(ia_local.programa(tmp_path, ia_local.PROGRAMA_VISAO))
    valor = lambda opcao: cmd[cmd.index(opcao) + 1]         # noqa: E731
    assert valor("--mmproj") == str(ia_local.visao(tmp_path)) and valor("--image") == str(tmp_path / "tela.png")
    assert valor("-sys") == "SISTEMA" and valor("-p") == "PEDIDO" and valor("-n") == "12"
    assert valor("--image-max-tokens") == str(ia_local.IMAGEM_TOKENS) and "--offline" in cmd
    assert "--jinja" in cmd and "<think>\n\n</think>" in valor("--chat-template")   # pensamento vazio


def test_ver_com_o_llama_falso(tmp_path):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("você está programando de novo?")])
    texto = ia_local.ver(tmp_path, "s", "p", tmp_path / "tela.png", programa_=prog)
    assert texto == "você está programando de novo?" and "--image" in chamadas.read_text(encoding="utf-8")


def test_resposta_sem_as_marcas():
    assert ia_local.resposta(resposta_qwen("Oi.").encode()) == "Oi."
    assert ia_local.resposta("Oi.<|im_end|>") == "Oi."
    assert ia_local.resposta("<think>\nThinking Process: ...") == ""         # começou a pensar: não serve


def test_gerar_com_o_llama_falso(tmp_path):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("Olá, mundo.")])
    assert ia_local.gerar(tmp_path, "P", programa_=prog) == "Olá, mundo."
    assert "--offline" in chamadas.read_text(encoding="utf-8")
    (tmp_path / "quebrado").mkdir()
    ruim, _ = llama_falso(tmp_path / "quebrado", ["erro"], codigo=3)
    with pytest.raises(RuntimeError, match="código 3"):
        ia_local.gerar(tmp_path, "P", programa_=ruim)
    with pytest.raises(RuntimeError, match="não abriu"):
        ia_local.gerar(tmp_path, "P", programa_=[str(tmp_path / "nao_existe")])


# ---------------- instalar ----------------

def test_baixar_confere_a_sha256(tmp_path):
    origem = tmp_path / "origem.bin"
    origem.write_bytes(b"conteudo do pacote")
    sha = ia_local.sha256_de(origem)
    destino = tmp_path / "baixado" / "pacote.bin"
    (destino.parent).mkdir()
    destino.with_name("pacote.bin.parte").write_bytes(b"lixo de uma tentativa antiga")
    assert ia_local.baixar(origem.as_uri(), destino, sha, lambda _l: None).read_bytes() == b"conteudo do pacote"
    with pytest.raises(RuntimeError, match="sha256"):
        ia_local.baixar(origem.as_uri(), tmp_path / "outro.bin", "0" * 64, lambda _l: None)
    assert not (tmp_path / "outro.bin").exists() and not (tmp_path / "outro.bin.parte").exists()


def _tar_com(caminho, nomes):
    with tarfile.open(caminho, "w:gz") as t:
        for nome in nomes:
            dados = b"#!/bin/sh\n"
            info = tarfile.TarInfo(nome)
            info.size, info.mode = len(dados), 0o755
            t.addfile(info, io.BytesIO(dados))


def test_extrair_tar_e_zip(tmp_path):
    _tar_com(tmp_path / "p.tar.gz", [f"llama-b1/{ia_local.PROGRAMA}", "llama-b1/libllama.dylib"])
    ia_local.extrair(tmp_path / "p.tar.gz", tmp_path / "a" / "llama")
    assert ia_local.programa(tmp_path / "a").name == ia_local.PROGRAMA
    if sys.platform != "win32":
        assert os.access(ia_local.programa(tmp_path / "a"), os.X_OK)          # continua executável
    with zipfile.ZipFile(tmp_path / "p.zip", "w") as z:
        z.writestr(ia_local.PROGRAMA + ".exe", b"MZ")
    ia_local.extrair(tmp_path / "p.zip", tmp_path / "b" / "llama")
    assert ia_local.programa(tmp_path / "b").name == ia_local.PROGRAMA + ".exe"


def test_extrair_recusa_arquivo_que_sai_da_pasta(tmp_path):
    _tar_com(tmp_path / "mau.tar.gz", ["../fora.sh"])
    with pytest.raises((tarfile.TarError, RuntimeError)):
        ia_local.extrair(tmp_path / "mau.tar.gz", tmp_path / "dentro")
    assert not (tmp_path / "fora.sh").exists()


def _baixar_falso(tmp_path, chamadas, falhar=()):
    pacote = tmp_path / "pacote_original.tar.gz"
    _tar_com(pacote, [f"llama-b1/{ia_local.PROGRAMA}", f"llama-b1/{ia_local.PROGRAMA_VISAO}"])

    def baixar(url, destino, sha, escrever, total=None):
        chamadas.append(url)
        if any(f in url for f in falhar):
            raise RuntimeError("a internet caiu")
        destino.parent.mkdir(parents=True, exist_ok=True)
        if url in (ia_local.MODELO_URL, ia_local.VISAO_URL):
            with open(destino, "wb") as f:                     # do tamanho certo, sem ocupar o disco
                f.truncate(ia_local.MODELO_BYTES if url == ia_local.MODELO_URL else ia_local.VISAO_BYTES)
        else:
            destino.write_bytes(pacote.read_bytes())
        return destino
    return baixar


def test_instalar_baixa_confere_testa_e_marca(tmp_path):
    pasta, chamadas, linhas = tmp_path / "ia_local", [], []
    ok = ia_local.instalar(pasta, linhas.append, baixar_=_baixar_falso(tmp_path, chamadas),
                           teste_=lambda p: (True, 0.8, "Oi."), sistema="darwin", maquina="arm64")
    assert ok and ia_local.instalada(pasta) and ia_local.visao_instalada(pasta)
    assert any("macos-arm64" in u and ia_local.LLAMA_VERSAO in u for u in chamadas)
    assert ia_local.MODELO_URL in chamadas and ia_local.VISAO_URL in chamadas
    assert any(linha.startswith("[3/4] Visão") for linha in linhas)
    assert not (pasta / "downloads").exists() or not any((pasta / "downloads").iterdir())   # pacote apagado
    info = json.loads((pasta / "instalado.json").read_text())
    assert info["llama"] == ia_local.LLAMA_VERSAO and info["revisao"] == ia_local.MODELO_REVISAO
    assert info["visao"] == ia_local.VISAO_ARQUIVO
    de_novo = []
    assert ia_local.instalar(pasta, linhas.append, baixar_=_baixar_falso(tmp_path, de_novo),
                             teste_=lambda p: (True, 0.8, "Oi."), sistema="darwin", maquina="arm64")
    assert de_novo == []                                     # tudo já estava lá


def test_instalacao_que_falha_nao_marca(tmp_path):
    pasta, linhas = tmp_path / "ia_local", []
    assert not ia_local.instalar(pasta, linhas.append, baixar_=_baixar_falso(tmp_path, [], falhar=("huggingface",)),
                                 teste_=lambda p: (True, 0.8, "Oi."), sistema="darwin", maquina="arm64")
    assert not ia_local.instalada(pasta) and any("continua de onde parou" in linha for linha in linhas)
    assert not ia_local.instalar(pasta, linhas.append, baixar_=_baixar_falso(tmp_path, []),
                                 teste_=lambda p: (False, 1.0, "nada"), sistema="darwin", maquina="arm64")
    assert not ia_local.instalada(pasta)
    assert not ia_local.instalar(pasta, linhas.append, sistema="freebsd", maquina="amd64")


def test_teste_do_instalador_com_o_llama_falso(tmp_path):
    prog, _ = llama_falso(tmp_path, [resposta_qwen("Oi.")])
    ok, _segundos, texto = ia_local.teste(tmp_path, lambda p, prompt, **kw: ia_local.gerar(p, prompt, programa_=prog, **kw))
    assert ok and texto == "Oi."


def test_linha_de_comando_diz_se_esta_instalada(tmp_path, capsys):
    assert ia_local.main(["--pasta", str(tmp_path)]) == 0
    assert "não instalada" in capsys.readouterr().out
    ia_local.main(["--remover", "--pasta", str(tmp_path)])
    assert not tmp_path.exists()


# ---------------- o pedido sai do que a rede sente ----------------

def test_descrever_o_que_a_rede_sente():
    texto = frases_ia.descrever({"emocao": "triste", "cansaco": 0.9, "carencia": 0.8, "tedio": 0.1,
                                 "atividade": "GAMING", "protesto": 3, "hora": 2})
    assert "triste" in texto and "cansado" in texto and "carente" in texto and "entediado" not in texto
    assert "jogando" in texto and "greve" in texto and "madrugada" in texto
    assert frases_ia.descrever({}) == "Agora você está tranquilo."
    assert "A pessoa" not in frases_ia.descrever({"atividade": "IDLE"})      # parado não diz nada
    assert set(config.EMOTIONS) <= set(frases_ia.EMOCOES)


@pytest.mark.parametrize("hora, parte", [(0, "madrugada"), (8, "manhã"), (14, "tarde"), (21, "noite")])
def test_parte_do_dia(hora, parte):
    assert parte in frases_ia.parte_do_dia(hora)


def test_montar_o_pedido():
    sistema, pedido = frases_ia.montar("Bryan", "Você odeia o cursor.", {"emocao": "bravo"},
                                       [f"frase {i}" for i in range(9)])
    assert "Você é Bryan" in sistema and "Você odeia o cursor." in sistema and "português do Brasil" in sistema
    assert "bravo" in pedido and pedido.count("- frase") == frases_ia.EXEMPLOS
    sistema, pedido = frases_ia.montar("X", None, {}, [])
    assert frases_ia.PERSONALIDADE_PADRAO in sistema and "Exemplos" not in pedido


@pytest.mark.parametrize("bruto, limpo", [
    ("eu só queria um amigo", "eu só queria um amigo"),
    ('"tô com sono"', "tô com sono"),
    ("Post-it: quantos TODOs você tem?", "quantos TODOs você tem?"),
    ("eu vi sua tela de novo, né?\ntem tempo pro navegador?", "eu vi sua tela de novo, né?"),
    ("se eu cair a culpa é da gravidade. mas o cursor é meu inimigo e o alt f4 também e eu vejo tudo", "se eu cair a culpa é da gravidade."),
    ("PROGRAMANDO.", None),                                  # curta demais
    ("compre meu curso em www.exemplo.com agora mesmo", None),
    ("palavra " * 30, None),
    ("", None),
    ("👀 🔥 💸", None),
    ("sinto muito, mas não sei se vou funcionar sem você. 😿", "sinto muito, mas não sei se vou funcionar sem você."),
    ("👍🏽 bom trabalho, chefe!", "bom trabalho, chefe!"),             # o modelo às vezes põe emoji
    ("olha isso ❤️ que lindo", "olha isso que lindo"),
])
def test_limpar_a_resposta(bruto, limpo):
    assert frases_ia.limpar(bruto) == limpo


def test_copiar_um_exemplo_nao_vale():
    assert frases_ia.limpar("O SEGREDO É TER MINDSET.", evitar=["o segredo é ter mindset"]) is None
    assert frases_ia.limpar("ENQUANTO VOCE DORME, EU ESCALO.", evitar=["ENQUANTO VOCÊ DORME, EU ESCALO."]) is None
    assert frases_ia.limpar("O SEGREDO É TER FOCO.", evitar=["o segredo é ter mindset"]) == "O SEGREDO É TER FOCO."


def test_pets_tem_personalidade_e_ela_e_validada():
    for pet in ("bryan", "jorge"):
        assert len(config.load_pet(Paths(root=RAIZ), pet)["personalidade"]) > 40
    assert "personalidade" not in config._pet_valido({"personalidade": 3})
    assert len(config._pet_valido({"personalidade": "x" * 5000})["personalidade"]) == 600


# ---------------- escrever e comentar (rodam na fila do preparo) ----------------

def _gerar_falso(respostas, erro=None):
    """Um ia_local.gerar/ver falso: devolve as respostas em ordem e anota as sementes."""
    chamadas = []

    def gerar(*a, **kw):
        chamadas.append(kw)
        if erro:
            raise RuntimeError(erro)
        return respostas[min(len(chamadas) - 1, len(respostas) - 1)]
    return gerar, chamadas


def test_escrever_devolve_a_frase_limpa(tmp_path):
    gerar, chamadas = _gerar_falso(['"eu só queria um amigo"'])
    assert frases_ia.escrever(tmp_path, "s", "p", gerar_=gerar) == ("eu só queria um amigo", None)
    assert chamadas[0]["tokens"] == frases_ia.TOKENS


def test_escrever_tenta_de_novo_com_outra_semente(tmp_path):
    gerar, chamadas = _gerar_falso(["OK.", "frase do exemplo aqui", "agora sim uma frase nova"])
    assert frases_ia.escrever(tmp_path, "s", "p", evitar=["frase do exemplo aqui"], gerar_=gerar) == (
        "agora sim uma frase nova", None)
    assert len({c["seed"] for c in chamadas}) == 3


def test_escrever_desiste_depois_das_tentativas(tmp_path):
    gerar, chamadas = _gerar_falso(["OK."])
    frase, motivo = frases_ia.escrever(tmp_path, "s", "p", gerar_=gerar)
    assert frase is None and "nenhuma das 3" in motivo and len(chamadas) == frases_ia.TENTATIVAS


def test_llama_que_quebra_nao_tenta_de_novo(tmp_path):
    gerar, chamadas = _gerar_falso([], erro="o llama.cpp saiu com o código 2")
    assert frases_ia.escrever(tmp_path, "s", "p", gerar_=gerar) == (None, "o llama.cpp saiu com o código 2")
    assert len(chamadas) == 1


def test_escrever_com_o_llama_falso_de_verdade(tmp_path, monkeypatch):
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("tô com saudade de você")])
    _usar_llama_falso(monkeypatch, prog)
    assert frases_ia.escrever(tmp_path, "s", "p", gerar_=ia_local.gerar) == ("tô com saudade de você", None)
    assert "<|im_start|>system" in chamadas.read_text(encoding="utf-8")


def test_comentar_apaga_o_print_sempre(tmp_path):
    print_ = tmp_path / "tela.png"
    print_.write_bytes(b"png")
    ver, chamadas = _gerar_falso(["você está programando de novo?"])
    assert frases_ia.comentar(tmp_path, "s", "p", print_, ver_=ver) == ("você está programando de novo?", None)
    assert not print_.exists() and chamadas[0]["tokens"] == frases_ia.TOKENS
    print_.write_bytes(b"png")
    ver, _ = _gerar_falso([], erro="passou de 60 s")
    assert frases_ia.comentar(tmp_path, "s", "p", print_, ver_=ver) == (None, "passou de 60 s")
    assert not print_.exists()


def test_comentar_nao_aceita_repetir_o_pedido(tmp_path):
    ver, _ = _gerar_falso(["Espie a tela acima e escreva o post-it.", "que tela bagunçada, hein"])
    _sistema, pedido = frases_ia.montar_visao("Bryan", None, {"emocao": "curioso"})
    assert frases_ia.comentar(tmp_path, "s", pedido, tmp_path / "x.png", ver_=ver)[0] == "que tela bagunçada, hein"


def test_montar_o_pedido_da_visao_protege_o_que_esta_na_tela():
    sistema, pedido = frases_ia.montar_visao("Bryan", "Você é teste.", {"emocao": "curioso", "atividade": "PROGRAMMING"})
    assert "Bryan" in sistema and "Você é teste." in sistema and "senhas" in sistema and "Não copie" in sistema
    assert "curioso" in pedido and pedido.endswith("Espie a tela acima e escreva o post-it.")


def test_frase_que_termina_em_dois_pontos_nao_serve():
    assert frases_ia.limpar("olha o que você está fazendo:") is None


# ---------------- no pet ----------------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _esperar(qapp, cond, tempo=15.0):
    fim = time.monotonic() + tempo
    while time.monotonic() < fim and not cond():
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


@pytest.fixture
def pet_app(qapp, tmp_path):
    from pestinha.app import PestinhaApp
    from pestinha.settings_store import SettingsStore
    paths = Paths(root=tmp_path, dados=tmp_path / "memory")
    (tmp_path / "pets").mkdir()
    (tmp_path / "pets" / "bryan.json").write_text(json.dumps({"nome": "Bryan", "personalidade": "Você é teste."}))
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS, travessuras=True))
    app = PestinhaApp(store, paths)
    yield app
    app.preparo.cancelar()
    app.floats.hidden_by_tray = True
    for w in list(app.floats.windows.values()):
        w.close()


def test_estado_para_a_ia_vem_da_rede_e_nao_tem_janela(pet_app):
    pet_app.pet_state.emotion = "curioso"
    estado = pet_app.estado_para_ia()
    assert estado["emocao"] == "curioso" and set(estado) == {
        "emocao", "cansaco", "carencia", "tedio", "atividade", "protesto", "hora"}
    assert estado["atividade"] in ("IDLE", "AWAY", "PROGRAMMING", "DESIGNING", "GAMING", "BROWSING", "MUSIC", "SOCIAL")


def _menu(pet_app, monkeypatch):
    from PySide6.QtWidgets import QMenu
    vistos = []

    class MenuAnotado(QMenu):
        def exec(self, *_a):
            vistos.append({acao.text(): acao.isEnabled() for acao in self.actions() if acao.text()})

    monkeypatch.setattr("pestinha.controle.interacao.QMenu", MenuAnotado)
    pet_app.show_pet_menu(None)
    return vistos[-1]


def test_botoes_no_menu(pet_app, monkeypatch, tmp_path):
    itens = _menu(pet_app, monkeypatch)
    assert itens["Escrever o que está sentindo (IA não instalada)"] is False
    assert "Espiar a tela e comentar (IA)" not in itens
    _instalada_falsa(pet_app.paths.ia_local, visao=False)
    itens = _menu(pet_app, monkeypatch)
    assert itens["Escrever o que está sentindo (IA)"] is True and "Espiar a tela e comentar (IA)" not in itens
    ia_local.visao(pet_app.paths.ia_local).write_text("")
    itens = _menu(pet_app, monkeypatch)
    assert itens["Espiar a tela e comentar (IA)"] is True
    pet_app.perms["bilhetes"] = False
    itens = _menu(pet_app, monkeypatch)
    assert itens["Escrever o que está sentindo (IA)"] is False and itens["Espiar a tela e comentar (IA)"] is False


def test_menu_mostra_o_que_esta_sendo_preparado(pet_app, monkeypatch):
    import threading
    from pestinha.mind.preparo import Tarefa
    _instalada_falsa(pet_app.paths.ia_local)
    solta = threading.Event()
    pet_app.preparo.pedir(Tarefa("post-it (bilhete_ia)", lambda c: solta.wait(5), lambda r: None))
    try:
        assert _menu(pet_app, monkeypatch)["Preparando: post-it (bilhete_ia)..."] is False
    finally:
        solta.set()


def test_botao_gera_e_ele_entrega_o_post_it(pet_app, qapp, tmp_path, monkeypatch):
    from pestinha.world.objetos import NoteThing
    prog, chamadas = llama_falso(tmp_path, [resposta_qwen("tô com saudade de você")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    pet_app.pet.show()
    lidos = []
    pet_app.mischief.bilhete_novo.connect(lidos.append)          # o que a voz leria
    pet_app.pet_state.emotion = "triste"
    pet_app.menu_frase_ia()
    assert _esperar(qapp, lambda: any(isinstance(t, NoteThing) for t in pet_app.mischief.things))
    assert [t.text for t in pet_app.mischief.things if isinstance(t, NoteThing)] == ["tô com saudade de você"]
    assert lidos == ["tô com saudade de você"]
    assert "triste" in chamadas.read_text(encoding="utf-8")


def test_post_it_nao_aparece_se_desligaram_no_meio(pet_app, qapp, tmp_path, monkeypatch):
    prog, _ = llama_falso(tmp_path, [resposta_qwen("frase que chegou tarde")])
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    pet_app.pet.show()
    pet_app.menu_frase_ia()
    pet_app.perms["bilhetes"] = False
    assert _esperar(qapp, lambda: not pet_app.preparo.ocupado())
    assert pet_app.mischief.things == []


def test_falha_avisa_na_bandeja(pet_app, qapp, tmp_path, monkeypatch):
    prog, _ = llama_falso(tmp_path, ["deu ruim"], codigo=2)
    _usar_llama_falso(monkeypatch, prog)
    _instalada_falsa(pet_app.paths.ia_local)
    avisos = []
    monkeypatch.setattr(pet_app.tray.icon, "showMessage", lambda *a: avisos.append(a[1]))
    pet_app.menu_frase_ia()
    assert _esperar(qapp, lambda: avisos)
    assert "código 2" in avisos[0] and pet_app.mischief.things == []
