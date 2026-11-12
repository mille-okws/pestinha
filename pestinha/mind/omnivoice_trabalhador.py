"""
TRABALHADOR DO OMNIVOICE - gera as falas da voz natural. Roda no ambiente da voz (voz_natural/ambiente),
não no do Pestinha: quem o abre é mind/voz_motor.py, com o Python daquele ambiente.

Conversa por linhas de JSON:
    entrada:  {"id": 1, "texto": "[sigh] ninguém lê o que eu escrevo", "velocidade": 0.85, "seed": 11,
               "referencia": ".../referencia.wav", "referencia_texto": "...", "saida": ".../abc.wav"}
    saída:    {"evento": "pronto", "dispositivo": "mps", "segundos": 7.6}     (uma vez, depois de carregar)
              {"id": 1, "ok": true, "segundos": 2.9, "tentativas": 1}
              {"id": 1, "ok": false, "erro": "..."}
Fecha sozinho quando o Pestinha fecha a entrada.

A voz vem do áudio de referência (clonagem): a mesma pessoa em todas as frases. Algumas seeds fazem o
modelo sair mudo ou falar só um pedaço; aí ele tenta a seed seguinte (até TENTATIVAS vezes).
No topo, só a biblioteca padrão e o numpy: o torch e o OmniVoice são importados em `main`, para
este arquivo poder ser lido e testado no ambiente do Pestinha.
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

TAXA = 24000                # Hz: o OmniVoice gera áudio mono a 24 kHz
TENTATIVAS = 5              # seeds tentadas antes de desistir de uma frase
FALA_MINIMA = 0.5           # fração do áudio que precisa ter voz (menos que isso: mudo ou cortado)
GUIDANCE = 3.0              # mais firme que o padrão (2.0): bem menos frases mudas na clonagem
VOLUME = 0.5                # pico do áudio final (o mesmo para todas as frases)
FOLGA_S = 0.1               # silêncio deixado nas pontas


def energia(audio, janela=1200):
    """Volume (RMS) em janelas de 50 ms, amostra a amostra."""
    audio = np.asarray(audio, dtype=np.float64)
    if len(audio) == 0:
        return audio
    janela = min(janela, len(audio))
    return np.sqrt(np.convolve(audio ** 2, np.ones(janela) / janela, mode="same"))


def fracao_de_fala(audio):
    """Quanto do áudio tem voz (0 a 1). Mudo ou quase mudo: 0."""
    rms = energia(audio)
    if len(rms) == 0 or rms.max() <= 1e-3:
        return 0.0
    return float((rms > 0.1 * rms.max()).mean())


def acabamento(audio):
    """Corta o silêncio das pontas (deixa uma folga) e deixa todas as frases com o mesmo volume."""
    audio = np.asarray(audio, dtype=np.float32)
    rms = energia(audio)
    if len(rms) == 0 or rms.max() <= 1e-3:
        return audio
    voz = np.where(rms > 0.1 * rms.max())[0]
    folga = int(FOLGA_S * TAXA)
    audio = audio[max(voz[0] - folga, 0): voz[-1] + folga]
    return (audio / max(float(np.abs(audio).max()), 1e-9) * VOLUME).astype(np.float32)


def sintetizar_com_tentativas(gerar, texto, seed, tentativas=TENTATIVAS):
    """Chama `gerar(texto, seed)` até sair fala de verdade. Devolve (áudio, tentativas) ou (None, tentativas)."""
    for n in range(1, tentativas + 1):
        audio = gerar(texto, seed + n - 1)
        if fracao_de_fala(audio) >= FALA_MINIMA:
            return acabamento(audio), n
    return None, tentativas


def atender(linha, sintetizar, salvar):
    """Uma linha de pedido -> o dicionário de resposta. `sintetizar(pedido)` -> (áudio, tentativas)."""
    try:
        pedido = json.loads(linha)
        ident = pedido["id"]
    except (ValueError, KeyError, TypeError):
        return {"ok": False, "erro": "pedido inválido"}
    inicio = time.monotonic()
    try:
        audio, tentativas = sintetizar(pedido)
        if audio is None:
            return {"id": ident, "ok": False, "erro": f"saiu mudo em {tentativas} tentativas"}
        salvar(Path(pedido["saida"]), audio)
    except Exception as erro:                              # um pedido ruim não derruba o trabalhador
        return {"id": ident, "ok": False, "erro": f"{type(erro).__name__}: {erro}"}
    return {"id": ident, "ok": True, "segundos": round(time.monotonic() - inicio, 2), "tentativas": tentativas}


def responder(resposta, saida=None):
    """Escreve uma linha de JSON na saída padrão (o Pestinha lê linha a linha)."""
    saida = saida or sys.stdout
    saida.write(json.dumps(resposta, ensure_ascii=False) + "\n")
    saida.flush()


def main(argv=None):
    """Carrega o modelo e atende os pedidos. `--teste` gera uma frase, diz se deu certo e sai."""
    import argparse
    import warnings

    warnings.filterwarnings("ignore")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")           # o modelo já está na pasta: nada de internet
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice

    args = argparse.ArgumentParser()
    args.add_argument("--modelo", required=True)
    args.add_argument("--teste", action="store_true")
    args = args.parse_args(argv)

    if torch.backends.mps.is_available():
        dispositivo, tipo = "mps", torch.float16
    elif torch.cuda.is_available():
        dispositivo, tipo = "cuda:0", torch.float16
    else:
        dispositivo, tipo = "cpu", torch.float32
    inicio = time.monotonic()
    modelo = OmniVoice.from_pretrained(args.modelo, device_map=dispositivo, dtype=tipo)
    carregou = round(time.monotonic() - inicio, 1)

    def gerar(texto, seed, **extra):
        torch.manual_seed(seed)
        return modelo.generate(text=texto, language="pt", guidance_scale=GUIDANCE,
                               postprocess_output=False, **extra)[0]

    if args.teste:
        audio, tentativas = sintetizar_com_tentativas(lambda t, s: gerar(t, s), "teste da voz natural.", 11)
        responder({"ok": audio is not None, "dispositivo": dispositivo, "segundos": carregou,
                   "tentativas": tentativas})
        return 0 if audio is not None else 1

    vozes = {}                                              # referência -> prompt de clonagem (calcula uma vez)

    def prompt_de(pedido):
        ref = Path(pedido["referencia"])
        chave = (str(ref), ref.stat().st_mtime_ns, pedido["referencia_texto"])
        if chave not in vozes:
            vozes[chave] = modelo.create_voice_clone_prompt(ref_audio=str(ref), ref_text=pedido["referencia_texto"])
        return vozes[chave]

    def sintetizar(pedido):
        prompt = prompt_de(pedido)
        return sintetizar_com_tentativas(
            lambda t, s: gerar(t, s, voice_clone_prompt=prompt, speed=float(pedido.get("velocidade", 1.0))),
            pedido["texto"], int(pedido.get("seed", 11)))

    def salvar(caminho, audio):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_name(caminho.name + ".tmp")
        sf.write(temporario, audio, TAXA, format="WAV")
        os.replace(temporario, caminho)                    # nunca fica um WAV pela metade no cache

    responder({"evento": "pronto", "dispositivo": dispositivo, "segundos": carregou})
    for linha in sys.stdin:
        if linha.strip():
            responder(atender(linha, sintetizar, salvar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
