# `pestinha/mind/`

> Gerado por `ferramentas/gerar_readmes.py` a partir das docstrings. Não edite à mão: rode o script.

Controladores de decisão: ligam o que a rede decide à cena (sono, mesa, protesto, travessuras, festa, revolução, cantinho do castigo), e a fila que prepara a IA local e a voz antes de algo aparecer.

**Pode importar de:** core, sense, body, world (e dos módulos compartilhados). A regra é verificada por `tests/test_arquitetura.py`.

| Arquivo | O que faz |
|---|---|
| `castigo_ctl.py` | Uma plaquinha de cartoon que você arrasta para onde quiser. |
| `espiar_ctl.py` | Quando o pet espia a tela para comentar o que você está fazendo (IA local com visão). |
| `fala_ctl.py` | Antes de um post-it, meme ou cartaz aparecer, prepara o que ele vai dizer. |
| `festa.py` | O fogo de artifício do pet feliz: a alegria da rede enche a euforia. |
| `frases_ia.py` | FRASES COM IA (em teste) - o pet escreve post-its com a IA local: sobre o que sente, ou sobre a tela. |
| `ia_local.py` | IA LOCAL (em teste) - um modelo de linguagem pequeno rodando no computador, com o llama.cpp. |
| `mesa.py` | O computadorzinho do pet: sentar e levantar do notebook. |
| `mischief_ctl.py` | Quando e como ele apronta, e o que a dispensa causa. |
| `omnivoice_trabalhador.py` | Gera as falas da voz natural. |
| `preparo.py` | O trabalho pesado antes de algo aparecer na tela: escrever com a IA local e gerar a fala. |
| `protest_ctl.py` | Liga o protesto (core/protesto.py) à cena: cartaz, estágio, repressão. |
| `revolucao.py` | As bolinhas de papel que o pet atira no cursor quando está em revolução. |
| `sleep.py` | Quando ele dorme, quando acorda, e o que acontece ao adormecer. |
| `voz.py` | O pet lê em voz alta os post-its e os cartazes, com a emoção que ele sente na hora. |
| `voz_instalacao.py` | Diz se este computador aguenta o OmniVoice e, se aguentar, instala. |
| `voz_motor.py` | Abre o trabalhador do OmniVoice (mind/omnivoice_trabalhador.py) para gerar UMA fala. |
