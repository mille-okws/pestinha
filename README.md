# Pestinha

Pets de tela para Windows, macOS e Linux, cada um com o próprio cérebro. São dois personagens por enquanto:

- **Bryan**, o original: uma telinha com dois olhos que mora no seu monitor principal. Cai, quica, pousa nas
  barras de título das janelas, brinca com uma bolinha, trabalha num notebook quando você programa, apronta
  com memes e post-its, protesta contra o cursor quando fica bravo e aprende com o seu carinho.
- **Jorge**, um personagem de sátira: um "coach" de finanças e IA que vive tentando vender mentorias para
  quem está na frente do computador. **Jorge não é uma referência a nenhum coach, empresa ou pessoa real.**
  É um personagem inventado para fazer piada com a cultura de promessas de enriquecimento rápido. Não vende,
  cobra nem pede nada de ninguém.

Os dois têm a mesma rede neural, mas cada um tem seu temperamento, seu conteúdo e sua memória, separados.
Quem decide o que o pet sente e faz é uma **rede neural pulsada** de 470 neurônios (integração e disparo com
vazamento), alimentada pelo que acontece no seu computador e pelo que você faz com ele. Algumas regras
do programa (limiares, o que pode ou não acontecer) são escritas à mão; a seção
[Como a decisão funciona](docs/ARQUITETURA.md#como-a-decisão-funciona) explica o que é aprendido e o que é regra.

> Projeto em desenvolvimento. Algumas coisas podem não funcionar direito e o comportamento pode
> mudar entre versões.

## Personagens

Cada personagem é um `pets/<pet>.json` (quem ele é) mais uma pasta `pets/<pet>/` (as frases, cartazes e
memes dele). Todos usam a mesma rede neural, mas cada um tem a própria memória: o que um aprende não
passa para o outro. Você escolhe o personagem em **Configurações**; a troca vale na próxima vez que abrir.
Para criar um, veja [pets/README.md](pets/README.md).

| Personagem | Quem é |
|---|---|
| **Bryan** | Revoltado contra o cursor, o Alt+F4 e o Gerenciador de Tarefas. Protesta, faz greve e revolução. |
| **Jorge** | Personagem de sátira. Não é referência a nenhum coach, empresa ou pessoa real. Os mesmos estágios viram prospecção, marketing agressivo, "assinatura premium" (só no cartaz) e colapso financeiro; ele atira panfletos de mentoria. É sátira: não vende, cobra nem bloqueia nada. Tem cinco memes felizes, contentes, curiosos e bravos próprios; as outras emoções ainda não têm. |

## O que o pet faz

| | |
|---|---|
| **Corpo** | Gravidade, quique, giro, pouso nas barras de título. Você arrasta, joga e gira com a rodinha. |
| **Emoções** | Saem dos motores da rede: feliz, contente, curioso, observando, bravo, triste, assustado, dramático, dormindo. |
| **Carinho** | Passe o mouse de um lado para o outro em cima dele: fecha os olhinhos de felicidade e aprende com isso. |
| **Bolinha** | Ele chuta e arremessa uma bolinha de tênis; você pode pegar, levar embora (ele reage) ou guardar. |
| **Notebook** | Quando você trabalha (VS Code, Visual Studio, PyCharm, Claude, Codex), ele pode sentar atrás do notebook e trabalhar junto. Você também pode pedir; ele decide se quer. |
| **Travessuras** | Traz memes, fotos e post-its para a tela. Com que frequência é decidido pela rede (tédio, curiosidade). |
| **Protesto** | Bravo por muito tempo: reclamação, manifestação, greve e revolução contra o cursor, com cartazes e bolinhas de papel. |
| **Tristeza** | Sozinho ou ignorado, fica triste, vai para o cantinho e cola bilhetes tristes. |
| **Cantinho do castigo** | Uma placa que você arrasta para onde quiser. Solte ele na frente dela e ele fica de castigo: olha para você, vira de costas, xinga em cartazes e, se a frustração durar, foge. Carinho faz ele perdoar. |
| **Sono e fogos** | Dorme quando a energia acaba. Muito feliz, solta fogos de artifício. |
| **Voz** | Opcional, no macOS: lê os post-its e os cartazes em voz alta, com a voz dele e a emoção da hora ([Voz](#voz)). |

Tudo o que ele aprende (carinho, condicionamento, o que deu certo nas travessuras, fugas do castigo)
fica salvo localmente e muda o jeito dele com o tempo.

## Requisitos

- Windows 10 ou 11, macOS (Quartz/pyobjc), Linux com X11 ou KDE Plasma 6 com Wayland.
- Python 3.11 ou mais novo.
- No Linux, para as janelas e o tempo ocioso: `xdotool`, `wmctrl` e `xprintidle`. Sem eles, o pet continua
  andando, mas não enxerga as janelas.
- No Wayland, o pet precisa do XWayland (no Arch e no CachyOS: `xorg-xwayland`); sem ele, avisa e não abre.
- No KDE Plasma 6 com Wayland, o pet roda pelo XWayland e um script do KWin, carregado enquanto ele está
  aberto, informa as janelas, o cursor e o atalho, e tira as janelas do pet da barra de tarefas. Não precisa
  dos comandos do X11. Para o tempo ocioso,
  instale também `pip install "pywayland>=0.4.19"` (fica fora do `requirements.txt` porque só tem pacote pronto
  para x86_64 com glibc 2.34 ou mais nova; sem ele, o pet age como se você estivesse sempre ativo).
- Cerca de 70 MB de RAM com ele rodando.
- Opcional, para a [voz natural](#voz-natural-omnivoice): Mac com Apple Silicon, 8 GB de RAM (16 GB é melhor)
  e uns 6 GB livres em disco.

## Instalação e uso

```bash
pip install -r requirements.txt
```
```bash
python main.py
```

Na primeira vez, um passo a passo explica o que ele vê e não vê, e depois abre a tela de permissões. Depois
de clicar em **Começar**, as próximas aberturas vão direto para o pet. A tela volta a aparecer se o pânico
tiver desligado o programa. Para abrir a tela de propósito:

```bash
python main.py --configurar
```

Com o programa aberto, as opções também ficam em **Configurações**, no ícone da bandeja. No Windows, é lá que
se marca **Abrir o Pestinha ao entrar no Windows**. Só uma cópia abre por vez.

### Como interagir

| Gesto | Efeito |
|---|---|
| Clique rápido | Cutucada |
| Passar o mouse de um lado para o outro em cima dele | Carinho |
| Segurar e arrastar / soltar rápido | Leva junto / arremessa |
| Rodinha do mouse | Gira |
| Botão direito | Menu: cutucar, carinho, bolinha, dormir, travessura, trabalhar, notebook, cantinho do castigo, painéis, configurações, esconder, fechar |

### Pânico

`Ctrl + Alt + Shift + B` desliga tudo na hora, e ele continua desligado até você religar em
Configurações.

### Modo teste

Desligado por padrão. Ligado, os tempos ficam curtos (emoções, travessuras e protesto acontecem em
segundos), os painéis de desenvolvimento ficam na tela (monitor neural e painel de protesto) e o
terminal mostra as decisões.

## Voz

Com **Falar os bilhetes e cartazes** ligado (em Configurações, grupo **Voz**; vem desligado), o pet lê em voz
alta cada post-it e cada cartaz que aparece. Por enquanto, só no macOS. Ele tem dois jeitos de falar:

| | Voz natural (OmniVoice) | Voz do sistema |
|---|---|---|
| Como soa | A voz de cada pet, com a emoção da hora: risada, resmungo, suspiro, susto | A voz do macOS (`say`), sempre igual |
| O que precisa | Instalar pelo menu (uns 4,5 GB, uma vez só) | Nada |
| Quando usa | Sempre que estiver instalada | Sem a voz natural, ou se ela falhar |

### Voz natural (OmniVoice)

O [OmniVoice](https://github.com/k2-fsa/OmniVoice) é um modelo que gera fala a partir de texto, roda no
seu computador e imita uma voz a partir de um áudio curto. Para instalar:

1. Abra **Configurações** e, no grupo **Voz**, clique em **Voz natural...**.
2. A tela confere se o computador aguenta e explica cada item:

   | Item | Precisa de | Por quê |
   |---|---|---|
   | Sistema | macOS 13 ou mais novo | No Windows e no Linux, a voz ainda não funciona |
   | Processador | Apple Silicon (M1 ou mais novo) | O modelo roda na GPU do Mac. O PyTorch atual não tem versão para Mac Intel |
   | Memória | 8 GB de RAM (com menos de 16 GB, ele avisa) | O modelo ocupa uns 3 GB enquanto a voz está ligada |
   | Espaço em disco | 6 GB livres | Baixa uns 4,5 GB |
   | Python | Rodando pelo código, Python 3.9 a 3.13 | O executável empacotado ainda não instala a voz natural |

3. Se estiver tudo certo, clique em **Baixar e instalar**. O andamento aparece na própria tela. Ele baixa as
   bibliotecas (PyTorch e OmniVoice, uns 1,2 GB, do PyPI) e o modelo (uns 3,3 GB, do Hugging Face) e, no fim,
   gera uma frase de teste. Se a internet cair, clique de novo: ele continua de onde parou.
4. Ligue **Falar os bilhetes e cartazes**. Na primeira fala, o modelo leva uns segundos para carregar.

Tudo fica na pasta `voz_natural/`, ao lado do programa, num ambiente Python separado. O Pestinha em si
não passa a depender do PyTorch. Depois de instalado, nada mais é baixado: o modelo roda sem internet.
**Apagar todos os dados** não apaga a voz natural; para tirar, use **Remover** na mesma tela ou apague a pasta
`voz_natural/` com o programa fechado.

Também dá para fazer pelo terminal, rodando pelo código:

```bash
python -m pestinha.mind.voz_instalacao              # só confere o computador
python -m pestinha.mind.voz_instalacao --instalar   # confere, baixa e instala
python -m pestinha.mind.voz_instalacao --remover    # apaga voz_natural/
```

**Como a emoção entra na fala.** Na hora em que o post-it aparece, a emoção do pet vira uma marca no começo
da frase e muda a velocidade. Os cartazes de protesto saem sempre bravos, e os de abandono, tristes.

| Emoção | Na fala | Velocidade |
|---|---|---|
| feliz | risada | um pouco mais rápida |
| contente, observando, dormindo | normal | normal (mais devagar com sono) |
| curioso | "oh?" | normal |
| bravo | resmungo | mais rápida |
| triste | suspiro | mais devagar |
| assustado | susto | bem mais rápida |
| dramático | suspiro | bem mais devagar |

Cada frase leva uns 3 segundos para ser gerada na primeira vez. Depois fica guardada em `memory/voz/<pet>/` e
toca na hora. Essa pasta pode ser apagada à vontade. Uma frase nova interrompe a anterior. Fechar o
post-it cala a fala dele, mesmo que ela ainda esteja sendo gerada.

### Trocar a voz de um pet

A voz de cada pet é um arquivo de áudio: o modelo imita esse áudio em todas as frases. Bryan e Jorge já vêm
com a deles, em `pets/bryan/voz/` e `pets/jorge/voz/`. Para trocar:

1. Arrume um áudio de **3 a 10 segundos** de **uma pessoa só** falando **português**, sem música, eco nem
   ruído. Pode ser uma gravação sua, ou uma voz gerada. Qualquer WAV serve (estéreo ou mono, qualquer taxa).
2. Salve como `pets/<pet>/voz/referencia.wav`, no lugar do que está lá.
3. Escreva em `pets/<pet>/voz/referencia.txt` **exatamente** o que é dito no áudio, palavra por palavra.
   Se o texto não bater com o áudio, a voz sai estranha.
4. Feche e abra o Pestinha. As falas antigas, que estavam guardadas, deixam de valer sozinhas.

Só use a voz de alguém com a permissão dessa pessoa.

O jeito de falar fica no `pets/<pet>.json`, no campo `voz`:

```json
"voz": {"sistema": "Eddy", "velocidade": 1.15, "seed": 11}
```

| Campo | Para que serve |
|---|---|
| `sistema` | A voz do macOS usada quando não há voz natural (veja as opções com `say -v '?'`; ele escolhe a de português do Brasil com esse nome) |
| `velocidade` | Velocidade da voz natural, de 0,5 a 2,0. A emoção multiplica esse valor |
| `seed` | Semente da geração (a mesma que criou a voz dele). Outro número muda a entonação das frases, não a voz, que vem do áudio |

Um pet sem `voz/referencia.wav` usa a voz do sistema, mesmo com a voz natural instalada.

## Frases com IA (em teste)

Em teste: o pet escreve um post-it novo sobre o que está sentindo, com um modelo de linguagem pequeno rodando no
seu computador. Quem decide o que ele sente continua sendo a rede neural: a emoção, o cansaço, a carência, o
tédio e o protesto saem dela. O modelo só põe isso em palavras e nunca decide nada.

Para instalar, por enquanto pelo terminal (rodando pelo código):

```bash
python -m pestinha.mind.ia_local --instalar
```

Ele baixa para a pasta `ia_local/`, ao lado do programa:

- o [llama.cpp](https://github.com/ggml-org/llama.cpp) já pronto, publicado pelo próprio projeto (13 a 25 MB,
  conforme o sistema). Nada é instalado no sistema nem no Python;
- o modelo [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) compactado
  ([GGUF Q4_K_M](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF), 1,3 GB).

Os dois têm versão fixa e só são usados se a sha256 bater com a anotada no código. No fim, ele gera uma
resposta de teste.

Depois, clique com o botão direito no pet e escolha **Escrever o que está sentindo (IA)**. Cada clique abre o
llama.cpp, que carrega o modelo, escreve e fecha: o modelo não fica ocupando memória. No macOS com Apple
Silicon, leva cerca de 1 segundo. Ele entrega a frase como um post-it e, com a voz ligada, lê em voz alta. O
item só funciona com **Travessuras** e **Bilhetes** ligados.

O pedido ao modelo leva só:

- a personalidade do pet, do campo `personalidade` do `pets/<pet>.json`;
- o que a rede sente agora;
- a categoria do que você está fazendo (programando, jogando...), nunca o nome nem o título da janela;
- a parte do dia;
- cinco frases do pet, como exemplo de estilo.

Respostas vazias, curtas ou compridas demais, com link ou copiadas de um exemplo são descartadas, e ele tenta
de novo, até 3 vezes. Para remover: `python -m pestinha.mind.ia_local --remover`, ou apague a pasta `ia_local/`.

## Privacidade

Ele roda só no seu computador e não envia nada para a internet. A única exceção é a instalação da voz
natural e da IA local, que você pede: elas baixam bibliotecas do PyPI, o llama.cpp do GitHub e os modelos do
Hugging Face. Lê o **nome** do programa em primeiro
plano, o tempo sem usar teclado e mouse, a posição do cursor e a geometria das janelas. **Nunca** lê
conteúdo nem título de janela. Tudo o que ele grava fica na pasta de dados e pode ser apagado pela tela de
configurações: `memory/`, rodando pelo código, ou `%LOCALAPPDATA%\Pestinha`, no executável do Windows.
Detalhes em [PRIVACIDADE.md](PRIVACIDADE.md).

## Personalizar

- **Memes, recadinhos e cartazes do Bryan:** pasta `pets/bryan/`, explicada em [pets/README.md](pets/README.md).
  Pode editar com ele aberto.
- **Bolinhas, notebook e suas fotos:** `assets/comum/`, valem para qualquer personagem
  ([assets/LEIA-ME.txt](assets/LEIA-ME.txt)).
- **Programas que ele reconhece:** `assets/comum/programas.json` soma programas à lista de trabalho, jogo, música etc.
- **Voz:** `pets/<pet>/voz/referencia.wav`, explicado em [Trocar a voz de um pet](#trocar-a-voz-de-um-pet).
- **Personalidade:** `pets/bryan.json` (semente da rede, temperamento, pesos de brincadeira, reação ao notebook).
- **Números do comportamento:** `pestinha/ajustes.py`, todos validados ao abrir.

## Estrutura

| Pasta | O que tem |
|---|---|
| `pestinha/` | O código, em camadas ([pestinha/README.md](pestinha/README.md)) |
| `assets/comum/` | Imagens da bolinha e do notebook, e suas fotos: valem para qualquer pet |
| `pets/` | Cada pet: `<pet>.json` (quem ele é) e `<pet>/` (frases, cartazes, memes e a voz dele) |
| `tests/` | Testes automáticos |
| `ferramentas/fuzz_pestinha.py` | Fuzzer: roda ações aleatórias e checa invariantes |
| `ferramentas/` | Geradores de documentação |
| `docs/` | Arquitetura, rede neural e relatórios ([docs/README.md](docs/README.md)) |
| `memory/` | Gerada em uso, com o que ele aprende. Não vai para o repositório |
| `voz_natural/` | Só se você instalar a voz natural: PyTorch e o modelo OmniVoice. Não vai para o repositório |
| `ia_local/` | Só se você instalar as frases com IA: llama.cpp e o modelo Qwen3.5-2B. Não vai para o repositório |

## Documentação

- [docs/ARQUITETURA.md](docs/ARQUITETURA.md): como as partes conversam.
- [docs/REDE_NEURAL.md](docs/REDE_NEURAL.md): canais, interneurônios, motores e decisões da rede.
- [pestinha/README.md](pestinha/README.md) e o README de cada pasta: o que cada arquivo faz.
- [CONTRIBUTING.md](CONTRIBUTING.md): como rodar os testes e contribuir.
- [CHANGELOG.md](CHANGELOG.md): o que mudou.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
```
```bash
python -m pytest -q
```

Os testes rodam sem abrir janelas (Qt em modo offscreen). Mais detalhes em [CONTRIBUTING.md](CONTRIBUTING.md).

### Gerar o executável

Há duas formas: gerar no seu computador (só o sistema em que você está) ou deixar o GitHub gerar os três.
O PyInstaller só gera o executável do sistema onde roda, por isso um Windows não gera o de Mac.

#### Opção 1: no seu computador

1. Instale as dependências de desenvolvimento (inclui o PyInstaller):

   ```bash
   pip install -r requirements-dev.txt
   ```

2. Gere o executável, no Windows:

   ```bash
   python -m PyInstaller --noconfirm --onefile --windowed --name Pestinha --distpath build/onefile --workpath build/work --specpath build --hidden-import win32timezone main.py
   ```

   No macOS e no Linux, use o mesmo comando sem `--windowed` e sem `--hidden-import win32timezone`. No Linux,
   acrescente `--add-data "$PWD/pestinha/plataforma/kwin_ponte.js:pestinha/plataforma"` (script do KWin).

3. O resultado fica em `build/onefile/` (`Pestinha.exe` no Windows, `Pestinha` nos outros).

4. Monte a pasta de entrega: copie o executável e as pastas `assets/` e `pets/` para uma mesma pasta.
   O programa lê o conteúdo dessas pastas ao lado do executável. No Windows, a memória fica em
   `%LOCALAPPDATA%\Pestinha`, a menos que já exista uma pasta `memory/` ao lado dele. Nos outros sistemas, a
   `memory/` é criada sozinha na primeira execução, então não copie a sua.

5. Opcional, no Windows: gere o instalador com o [Inno Setup 6](https://jrsoftware.org/isinfo.php). Ele usa o
   executável do passo 3, instala só para o usuário atual e não pede administrador:

   ```bash
   ISCC instalador/pestinha.iss
   ```

   O resultado fica em `instalador/saida/`.

#### Opção 2: pelo GitHub (os três sistemas de uma vez)

O workflow `.github/workflows/executaveis.yml` gera Windows, macOS e Linux em máquinas do próprio GitHub.

1. Suba o repositório para o GitHub (`git push`).
2. Para gerar sem criar versão: na aba **Actions**, escolha **executáveis**, clique em **Run workflow**.
3. Para gerar e publicar uma versão: crie uma tag e envie. Por exemplo:

   ```bash
   git tag v0.8.0
   git push origin v0.8.0
   ```

4. Ao terminar (alguns minutos), a execução tem três artefatos, um por sistema, com a pasta pronta
   (executável + `assets/` + `pets/`). Baixe pela própria página da execução, na seção **Artifacts**.

Para distribuir para quem não é do projeto, publique esses artefatos na aba **Releases** (use "Draft a new release"
na tag criada), e não dentro do repositório: cada executável tem cerca de 60 MB.

#### Depois de gerar

- Para testar sem misturar com a sua memória, crie uma pasta `memory/` vazia ao lado do executável de teste.
- O executável não é assinado: o Windows e o macOS avisam na primeira execução. No macOS, a permissão de
  Acessibilidade é necessária para o atalho Ctrl+Alt+Shift+B; no Linux, o atalho e as janelas precisam de
  `xdotool`, `wmctrl` e `xprintidle`.

## Licença

O código do Pestinha é software livre, sob a [GNU General Public License v3.0 ou posterior](LICENSE)
(GPL-3.0-or-later). Você pode usar, estudar, modificar e redistribuir, mas toda versão distribuída,
modificada ou não, precisa continuar aberta e sob a mesma licença.

As imagens e os textos de `assets/` não estão cobertos por esta licença.

A voz natural usa o [OmniVoice](https://github.com/k2-fsa/OmniVoice), que não vem com o Pestinha: ele é
baixado na instalação. O código do OmniVoice é Apache-2.0, mas o modelo é
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), **só para uso não comercial**. O tokenizador
de áudio que vem com ele tem a licença própria da Boson AI. As vozes do Bryan e do Jorge
(`pets/*/voz/referencia.wav`) foram geradas com esse modelo, então valem as mesmas condições.

As frases com IA usam o [llama.cpp](https://github.com/ggml-org/llama.cpp) (MIT) e o
[Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) (Apache-2.0), que também não vêm com o Pestinha: são
baixados na instalação. Os dois permitem uso comercial.

## Limitações conhecidas

- Linux ainda não foi testado numa máquina real: a parte de leitura das janelas e do teclado foi escrita e
  testada só nas partes de texto (ver `tests/test_plataforma.py`). No macOS, `tests/test_macos_real.py` abre
  janelas de verdade e lê o sistema num Mac real, inclusive no CI.
- No macOS, o pet precisa da permissão de Acessibilidade para o atalho Ctrl+Alt+Shift+B funcionar.
- No Wayland fora do KDE Plasma 6 (GNOME, Sway, Hyprland), o pet não enxerga janelas nem o tempo ocioso, e o
  atalho global não funciona.
- Pouco testado com escala de tela acima de 100% e com vários monitores. A tela cheia num monitor esconde o
  pet em todos.
- Jogos em janela sem borda podem não ser detectados como tela cheia.
- O executável não é assinado; o Windows pode avisar na primeira execução.
- A voz só funciona no macOS. A voz natural precisa de Apple Silicon e só instala rodando pelo código, não pelo
  executável. As marcas de emoção do modelo foram treinadas em inglês e chinês: em português, às vezes a
  risada ou o suspiro saem fracos.
- As frases com IA são um teste: só foram testadas no macOS com Apple Silicon (o instalador também baixa o
  llama.cpp do Windows e do Linux, sem teste nesses sistemas) e só instalam pelo terminal. O modelo é pequeno: às
  vezes erra a ortografia, principalmente em maiúsculas (Jorge), ou escreve algo sem sentido.
