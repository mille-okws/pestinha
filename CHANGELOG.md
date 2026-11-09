# Histórico de versões

## Sem enxurrada de avisos do perfil de cor no terminal

- Com um monitor cujo perfil de cor não tem nome (o macOS gera alguns assim), o Qt escrevia
  `qt.gui.icc: fromIccProfile: Failed to parse description` a cada redesenho de uma janela nesse monitor,
  e o terminal enchia enquanto o pet estava lá. As cores sempre ficaram certas: o aviso agora fica desligado.
  Para ver de novo, rode com `QT_LOGGING_RULES=qt.gui.icc.warning=true`.

## Fala preparada antes, frases escolhidas pela rede e espiar a tela (em teste)

- **A fala é gerada antes de o post-it ou cartaz aparecer.** Com a voz natural, uma fila prepara tudo antes:
  o motor da voz abre, carrega o modelo, gera o áudio e fecha; só então o post-it (ou cartaz) aparece, já com o
  áudio, e o arquivo é apagado quando termina de tocar. O modelo da voz não fica mais carregado o tempo todo
  e nenhuma fala fica guardada (acabou o cache em `memory/voz/<pet>/`).
- **Frase com IA + voz, um modelo por vez:** a IA local escreve e fecha, a voz gera e fecha, e o post-it
  aparece com o áudio. A IA e a voz nunca ficam na memória juntas (conferido no macOS: até 2,2 GB da IA e
  3,4 GB da voz, nunca ao mesmo tempo).
- **A rede escolhe frase nova ou já escrita:** novo neurônio motor `INVENTAR` (um modulador, que não compete
  com as decisões). A taxa dele vira a chance de a IA escrever uma frase nova, em vez de uma de
  `recadinhos.txt`. A memória registra as frases inventadas como `bilhete_ia`. Opção **Inventar frases novas**
  (ligada por padrão, só vale com a IA local instalada).
- **Espiar a tela (em teste):** o Qwen3.5-2B enxerga imagens. Com a parte da visão (`mmproj-F16.gguf`, 0,7 GB,
  agora baixada pelo instalador), o pet tira um print da tela, a IA comenta, o print é apagado e o comentário
  vira um post-it. Quem decide quando é o novo neurônio de decisão `ESPIAR` (curioso e com novidade na tela),
  no máximo uma vez a cada 10 minutos. Opção **Espiar a tela e comentar**, desligada por padrão; também pelo
  menu do pet. No macOS, pede a permissão de Gravação de Tela só quando você liga a opção ou usa o menu.
- A rede passa de 470 para 490 neurônios (17 populações motoras).
- O menu do pet mostra **Preparando...** enquanto algo está na fila. Pânico, fechar e remover a voz natural
  cancelam a fila e apagam os áudios.
- Removido o `QProcess` das frases com IA: a fila roda os programas numa thread só, com `subprocess`.
- **Só a cena fica na frente de tudo:** o pet, a bolinha, o notebook, os fogos, os post-its, memes e cartazes e
  a plaquinha do castigo. O monitor neural e o painel de protesto ficam no nível normal: quando você usa outro
  programa, ele fica por cima deles (no macOS, sem sumir da tela). No menu do pet, o painel vem para a frente,
  e **Fechar o monitor neural** / **Fechar o painel de protesto** fecha.
- **Memes e fotos falam** (com a voz ligada): uma fala de `pets/<pet>/falas_memes.txt` (novo, para o Bryan e o
  Jorge) ou, quando a rede quer inventar e a IA local enxerga, um comentário da IA sobre a própria imagem (ela olha
  uma cópia; o meme fica intacto). Com a voz natural, o meme espera a fala, como os post-its.
- **Testar meme** e **Testar meme com IA** (Configurações > Travessuras): ele traz um meme na hora, com a fala, e
  a tela diz o que está acontecendo. Não conta como travessura para a rede aprender.
- **Greve e revolução como palavra de ordem:** o cartaz é falado uma vez, sem pressa e mais alto, e repetido
  depois de meio segundo (o mesmo áudio). Quantas vezes repete (0 a 5) e a pausa, em milissegundos (0 a 10.000),
  ficam em Configurações > Voz. Se o cartaz sair antes, ele não repete. Os outros cartazes de protesto saem
  bravos, com exclamação. O trabalhador da voz aceita `volume` no pedido.
- **O cantinho do castigo fala:** o cartaz é falado com drama (ou bravo, com raiva), com a fala preparada antes,
  como os outros cartazes. O xingamento é censurado: os símbolos viram "piii", e o que é só símbolo vira um
  resmungo da seção nova `[resmungo]` do `cartazes.txt` (escrita para o Bryan e o Jorge).
- **Frases da IA sem emoji:** o pedido já dizia "sem emoji", mas o modelo às vezes punha; agora eles são tirados.
- **Configurações > Ao abrir:** **Começar com o notebook na tela** e **Começar com a bolinha na tela** (os dois
  ligados por padrão).
- **Configurações:** a janela ficou mais larga e sem rolagem para os lados.
- **Sem "Esconder":** saiu o Esconder/Mostrar da bandeja e o "Esconder (volta pela bandeja)" do menu do pet, que
  podiam deixar o pet sumido. O "Fechar" do menu do pet, que também só escondia, virou **Sair** e fecha o programa,
  igual ao Sair da bandeja.
- **Modo teste:** o monitor neural e o painel de protesto não abrem mais sozinhos; abrem pelo menu ou pela
  bandeja. Quem quiser o jeito antigo liga **Abrir os painéis no modo teste** (desligado por padrão); abertos
  assim, agora dá para fechar pelo menu.
- **Modo teste:** o último print que a IA olhou fica em `memory/logs/ultima_espiada.png` (e em **Ver o último
  print (teste)** no menu), para conferir a captura. Some ao desligar o Modo teste.

## Frases com IA (em teste)

- Novo item **Escrever o que está sentindo (IA)** no menu do pet: ele escreve um post-it novo sobre o que
  sente, com o Qwen3.5-2B rodando no computador pelo llama.cpp. A rede neural decide o que ele sente
  (emoção, cansaço, carência, tédio, protesto); o modelo só escreve.
- Instalação pelo terminal: `python -m pestinha.mind.ia_local --instalar`. Baixa o llama.cpp pronto e o modelo
  para `ia_local/`, com versão fixa e sha256 conferida, sem instalar nada no sistema nem no Python.
- Cada frase abre o llama.cpp, gera e fecha (cerca de 1 s no macOS com Apple Silicon), então o modelo não fica
  na memória. Respostas ruins são descartadas, e ele tenta de novo até 3 vezes.
- Novo campo `personalidade` no `pets/<pet>.json`, usado no pedido ao modelo.

## Voz: o pet lê os post-its e os cartazes

- Nova opção **Falar os bilhetes e cartazes** (macOS, desligada por padrão). O pet lê em voz alta cada
  post-it e cada cartaz que aparece. Uma frase nova interrompe a anterior, e fechar o post-it cala a fala.
- **Voz natural** com o [OmniVoice](https://github.com/k2-fsa/OmniVoice), rodando no computador. Cada pet fala
  com a voz dele e com a emoção da hora, em forma de risada, resmungo, suspiro ou susto e da velocidade.
  Os cartazes de protesto saem bravos e os de abandono, tristes.
- Tela **Voz natural...** em Configurações: confere se o computador aguenta (macOS 13+, Apple Silicon,
  memória, disco, Python), explica o que vai ser baixado (uns 4,5 GB), instala mostrando o andamento e
  remove. Também pelo terminal: `python -m pestinha.mind.voz_instalacao [--instalar | --remover]`.
- O motor fica num ambiente Python separado (`voz_natural/`), num processo à parte. O Pestinha não passa a
  depender do PyTorch, e o pet não trava enquanto a fala é gerada. As falas geradas ficam em
  `memory/voz/<pet>/` e tocam na hora da segunda vez.
- Bryan e Jorge vêm com a voz deles em `pets/<pet>/voz/referencia.wav`. Para trocar a voz, troque esse
  arquivo e o `referencia.txt`, como explica o README.
- Sem a voz natural (ou se ela falhar), o pet usa a voz do sistema (`say`), escolhida no campo `voz` do
  `pets/<pet>.json`.

## macOS: o pet fica na frente de tudo

- O pet, a bolinha e os painéis sumiam ao clicar em outro programa: o `Qt.Tool` vira um `NSPanel` com
  `hidesOnDeactivate`. Agora ficam na tela, em todos os Spaces e sobre programas em tela cheia.
- Clicar no pet não ativa mais o programa, como já acontecia no Windows. As Configurações pedem o foco ao abrir.
- Testes no macOS com janelas reais (`tests/test_macos_real.py`), também no CI: as janelas do pet continuam na tela
  quando outro programa ganha o foco, o atalho de pânico registra e as leituras do sistema têm o formato certo.

## 0.8.0 — melhorias para o Windows

### Correções
- Janela maximizada em monitor sem barra de tarefas (ou com a barra oculta) não conta mais como tela cheia.
- O pet pousa em janelas de todos os monitores, cada um com a própria escala.
- Falha ao apagar os dados pela bandeja agora avisa quais arquivos ficaram, também no executável sem terminal.
- Só uma cópia abre por vez, para duas não gravarem na mesma memória.
- Sem permissão de escrita na pasta de dados, a bandeja avisa em vez de perder o aprendizado em silêncio.
- Erros não tratados vão para o log, e um erro ao salvar não impede as outras gravações nem o fechamento.
- Religar depois do pânico desloca os prazos pelo tempo parado, como já acontecia com a pausa.

### Melhorias
- O registro da rotina vem desligado e passa a se chamar "Registrar minha rotina", porque nada usa esses dados
  ainda. Quem já tinha a opção salva continua como estava.
- A tela de permissões só aparece na primeira vez, após o pânico ou com `--configurar`.
- Opção de abrir ao entrar no Windows, em Configurações.
- O executável do Windows grava em `%LOCALAPPDATA%\Pestinha`. Uma `memory/` já existente ao lado dele continua valendo.
- Instalador para Windows com Inno Setup (`instalador/pestinha.iss`).
- Mais programas reconhecidos (Cursor, Windsurf, Zed, Windows Terminal, IDEs JetBrains, Sublime, Notepad++), e
  `assets/comum/programas.json` para acrescentar outros.
- Design, vídeo e 3D passam a contar como trabalho: Blender, Figma, Photoshop, Illustrator, After Effects,
  Premiere, DaVinci Resolve, CapCut, Krita, Inkscape e os fatiadores Bambu Studio, OrcaSlicer, PrusaSlicer
  e Cura. Também Antigravity, Kiro, Trae e Android Studio como programação, e jogos populares (LoL,
  Roblox, Minecraft, Fortnite, Apex, Dota 2, Rocket League, Overwatch, GTA V, Elden Ring) como jogo.

## Suporte a macOS e Linux

- Toda a leitura do sistema (programa em primeiro plano, tempo ocioso, janelas, tela cheia, foco e o atalho
  de pânico) passa para `pestinha/plataforma/`, com um módulo por sistema. O resto do código não sabe
  qual sistema está rodando.
- O Windows continua com o mesmo comportamento: o código foi movido, não reescrito.
- macOS: Quartz e AppKit (pyobjc), tempo ocioso pelo `ioreg` se não houver pyobjc. Atalho via pynput.
- Linux (X11): xdotool, wmctrl e xprintidle; atalho via pynput. Em Wayland, o pet não enxerga janelas
  nem o tempo ocioso, e o atalho não funciona.
- A checagem de atividade reconhece os nomes de programa dos três sistemas (com ou sem `.exe`).

## Renomeação para Pestinha

- O programa e o pacote Python passam a se chamar `pestinha/` (antes `bryan/`); a classe principal é
  `PestinhaApp`; o executável, o log e a documentação usam Pestinha.
- Bryan continua sendo o nome do primeiro personagem: `pets/bryan.json`, `pets/bryan/`, a memória
  `memory/pets/bryan/` e os arquivos de conteúdo dele não mudaram.
- Os comentários e textos que falavam do pet em geral passam a dizer "o pet".

## 0.7.0 — primeira versão pública (em preparação)

### O que ele faz
- Pet de tela com corpo físico: gravidade, quique, giro, pouso nas barras de título, arraste e arremesso.
- Rede neural pulsada de 470 neurônios LIF, com 30 canais sensoriais, 10 populações de interneurônios
  e 15 motores (8 de expressão e 7 de decisão).
- Emoções vindas dos motores; carinho com olhinhos fechados de felicidade.
- Bolinha de tênis, notebook de trabalho (VS Code, Visual Studio, PyCharm, Claude, Codex) e pedido de
  trabalho que ele pode recusar.
- Travessuras com memes, fotos, post-its e bilhetes tristes, com frequência decidida pela rede.
- Protesto em estágios até a revolução contra o cursor, com cartazes e bolinhas de papel.
- Cantinho do castigo: placa arrastável, perdão por carinho, fuga por vontade acumulada, rancor, receio,
  medo condicionado da placa e cartazes de xingamento.
- Aprendizado: habituação, regra de três fatores, condicionamento Rescorla–Wagner, memória episódica.
- Pânico (`Ctrl + Alt + Shift + B`), pausa, modo teste, monitor neural e painel de protesto.

### Memória por personagem
- Cada personagem tem a sua memória em `memory/pets/<pet>/` (rede e os sete arquivos de memória); o que
  é do app (permissões, rotina, painéis, log) continua em `memory/`.
- Migração automática da versão antiga: copia, confere, guarda os originais em `memory/legado/<pet>/` e
  só então marca como migrado. Conflito ou falta de permissão não sobrescrevem nada: ele segue com os
  arquivos antigos e avisa na bandeja.

### Conteúdo por personagem
- Frases, cartazes e memes de cada personagem ficam em `pets/<pet>/`; imagens neutras (bolinhas, notebook)
  e suas fotos em `assets/comum/`. Um personagem nunca usa o conteúdo de outro: sem conteúdo próprio, usa
  frases neutras ou não faz aquela travessura.
- Os cartazes do cantinho do castigo saíram do código para as seções `[castigo]` e `[xingamento]` do
  `cartazes.txt` do pet.

### Escolha do personagem
- O programa passa a se chamar **Pestinha**; o Bryan é o primeiro personagem.
- O personagem é escolhido em Configurações (vale ao reabrir). Só `pets/<pet>.json` vira opção.
- Os textos usam o nome do personagem onde é ele que fala (apresentação, "Estou aqui", notebook, monitor
  neural, painel de protesto) e o nome do programa no resto (configurações, bandeja, pânico).
- O log passa a ser `memory/logs/pestinha.log`; o executável, `Pestinha.exe`.

### Jorge
- Segundo personagem: coach de finanças e IA, trambiqueiro. Mesma rede e mesmos estágios do Bryan, com
  outra semente, outro temperamento e conteúdo próprio (recadinhos, bilhetes tristes, cartazes de todos os
  estágios e do cantinho, e um panfleto de mentoria no lugar da bolinha de papel). Cinco memes para cada uma de felizes, contentes, curiosos e bravos, em `pets/jorge/memes/`.
- `ferramentas/medir_cartazes.py` confere, com as fontes de verdade, se cada cartaz cabe na placa.
- `ferramentas/gerar_panfleto.py` desenha o panfleto do Jorge.

### Cores e acessórios
- Cada pet pode ter as próprias cores (moldura, tela, olhos) e acessórios (óculos, gravata) no campo
  `aparencia` do `.json`. Os acessórios são uma camada por cima do rosto; olhos e expressões não mudam.
- O Jorge tem moldura e olhos dourados e gravata vermelha. O Bryan continua igual.

### Licença
- Código sob GPL-3.0-or-later (`LICENSE`).

### Qualidade
- Arquitetura em camadas verificada por teste; `app.py` dividido em composição e mixins de sessão e
  interação.
- Persistência validada: escrita atômica, recusa de `NaN`, carga tudo-ou-nada.
- Cinco rodadas de auditoria, com cada bug corrigido coberto por teste, registradas em `docs/auditorias/`.
- Suíte de testes, bateria de 100 cenários do cantinho e fuzzer com invariantes.
