"""Valida os memes em pixel art do Eddie e exporta o catálogo das frases.

As artes foram geradas com imagegen integrado, usando os prompts em
pets/eddie/memes/prompts.json. Este script não sobrescreve as imagens.
Uso: python ferramentas/gerar_memes_eddie.py
     python ferramentas/gerar_memes_eddie.py --exportar-catalogo /caminho/catalogo.json
"""

import argparse
import json
from pathlib import Path

from PySide6.QtGui import QImage

RAIZ = Path(__file__).resolve().parents[1]
PASTA = RAIZ / "pets" / "eddie" / "memes"

MEMES = {
    "trabalhando": [
        ("IDE aberta.", "Qual é o bug que você vai criar hoje?", "curioso"),
        ("Só uma alteração pequena.", "Últimas palavras antes do incidente.", "assustado"),
        ("Você: vou só renomear.", "Git: 47 arquivos alterados.", "dramatico"),
        ("Debugger ligado.", "O bug: nunca nem estive aqui.", "observando"),
        ("Bom dia, dev.", "Já tomou café ou vai codar no ódio?", "contente"),
        ("Abriu outra aba.", "Agora são 12 soluções e nenhuma funciona.", "curioso"),
    ],
    "notebook": [
        ("Licença, chegou o sênior.", "Deixa que eu arrumo esse seu código ruim...", "contente"),
        ("Pair programming.", "Você digita. Eu julgo.", "observando"),
        ("Já corrigi o erro.", "Agora temos um erro novo.", "feliz"),
        ("Não me interrompe.", "Tô encarando o código até ele confessar.", "bravo"),
    ],
    "feliz": [
        ("O build passou!", "Ninguém encosta em nada.", "feliz"),
        ("Resolvi o bug.", "Não sei como. Mas resolvi.", "feliz"),
    ],
    "contente": [
        ("Na minha máquina funciona.", "Vamos entregar a minha máquina.", "contente"),
        ("Code review aprovado.", "Até desconfiei de mim.", "contente"),
    ],
    "curioso": [
        ("Quem escreveu isso?", "Git blame: eu. Ontem.", "curioso"),
        ("E se eu tirar esse if?", "O início de toda tragédia.", "curioso"),
    ],
    "observando": [("TODO: arrumar depois.", "O depois já tem 3 anos.", "observando")],
    "bravo": [
        ("Não é o cache.", "Era o cache.", "bravo"),
        ("Só faltava um ponto e vírgula.", "Três horas da minha vida.", "bravo"),
    ],
    "triste": [("PR em draft.", "Igual à minha vontade de sair da cama.", "triste")],
    "assustado": [("Deploy na sexta.", "O fim de semana pediu demissão.", "assustado")],
    "dramatico": [("Apaguei um console.log.", "Parou de funcionar.", "dramatico")],
}


def catalogo():
    """Frases aprovadas e caminhos estáveis; as imagens podem mudar sem trocar as piadas."""
    return [
        dict(arquivo=f"{pasta}/eddie_{i:02}.png", setup=setup, punchline=punchline, emocao=emocao)
        for pasta, memes in MEMES.items()
        for i, (setup, punchline, emocao) in enumerate(memes, 1)
    ]


def validar():
    """Verifica catálogo, prompts e carregamento das artes sem alterar os arquivos."""
    manifest = json.loads((PASTA / "prompts.json").read_text(encoding="utf-8"))
    esperado = catalogo()
    recebido = [{k: item[k] for k in ("arquivo", "setup", "punchline", "emocao")}
                for item in manifest["assets"]]
    if recebido != esperado:
        raise ValueError("Os prompts não correspondem às frases aprovadas.")
    for item in esperado:
        imagem = QImage(str(PASTA / item["arquivo"]))
        if imagem.isNull() or imagem.width() != imagem.height() or imagem.width() < 1024:
            raise ValueError(f"Arte ausente, inválida ou fora do formato quadrado: {item['arquivo']}")
    return len(esperado)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exportar-catalogo", type=Path)
    args = parser.parse_args()
    if args.exportar_catalogo:
        args.exportar_catalogo.write_text(json.dumps(catalogo(), ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
        print(f"Catálogo exportado: {args.exportar_catalogo}")
    else:
        print(f"{validar()} memes em pixel art validados. Nenhuma imagem foi sobrescrita.")


if __name__ == "__main__":
    main()
