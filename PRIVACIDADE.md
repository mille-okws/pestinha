# Privacidade do Pestinha

O Pestinha roda só no seu computador. Ele não envia nada para a internet.

Ele só usa a internet quando você pede para instalar a **voz natural** (Configurações > Voz natural...) ou
as **frases com IA** (`python -m pestinha.mind.ia_local --instalar`). A voz natural baixa bibliotecas do
PyPI (PyTorch e OmniVoice) e o modelo do Hugging Face. As frases com IA baixam o llama.cpp do GitHub e o modelo
do Hugging Face. Ele não manda nenhum dado seu, só os pedidos de download normais (o seu IP fica visível para
esses sites, como em qualquer download). Depois de instalados, os modelos rodam sem internet.

## O que ele lê

- O **nome** do programa em primeiro plano (por exemplo `code.exe`). Nunca o título nem o conteúdo da janela.
- Quanto tempo você está sem usar teclado ou mouse, e se o teclado ou o mouse foram usados agora.
- A posição do cursor, para saber se ele encostou na bolinha, se você está em cima do pet (carinho,
  cutucar) ou perto dele no cantinho do castigo.
- Se uma janela cobre a tela inteira (para não aparecer em jogos ou apresentações).
- A posição e o tamanho das janelas abertas, para ele poder pousar nas barras de título.
- No KDE Plasma com Wayland, essas leituras vêm de um script do KWin (`pestinha/plataforma/kwin_ponte.js`)
  que só existe enquanto o pet está aberto e manda geometria, pid e estado das janelas, nunca títulos.

Ele **não** lê o título de nenhuma janela, página, documento ou conversa. O conteúdo da tela, só com
**Espiar a tela e comentar** (veja abaixo), que vem desligado.

## O que ele grava

Tudo fica na pasta de dados, mostrada na tela de configurações. Ela é `memory/` ao lado do programa ou, no
executável do Windows, `%LOCALAPPDATA%\Pestinha` (a menos que já exista uma `memory/` ao lado dele). Abaixo,
`memory/` significa essa pasta. Desinstalar o programa não apaga esses dados.

Do app e seu, direto em `memory/`:

| Arquivo | Conteúdo |
|---|---|
| `permissions.json` | As opções que você escolheu |
| `timeline.csv` | Uma linha por minuto: hora, categoria de programa, trocas de janela, ocioso. Só com "Registrar minha rotina" ligado, que vem desligado. O pet ainda não usa esse histórico |
| `panels.json` | Posição dos painéis, do notebook e da placa |
| `logs/pestinha.log` | Mensagens do programa e erros inesperados (sem conteúdo de janelas) |
| `logs/voz_natural.log` | Só com a voz natural: avisos e erros do modelo |
| `voz/<pet>/` | Só com a voz natural: o áudio da fala que vai tocar agora. Ele é gerado antes de o post-it aparecer e apagado assim que termina de tocar (ou se o post-it não aparecer). Nada fica guardado; sobras de quando o programa fechou no meio são apagadas ao abrir |

De cada personagem, em `memory/pets/<pet>/` (um personagem não lê a memória do outro):

| Arquivo | Conteúdo |
|---|---|
| `nervous.json` | Estado da rede neural (habituação e aprendizado) |
| `episodes.jsonl`, `preferences.json` | Resultado de cada travessura e preferências aprendidas |
| `conditioning.json` | O que ele aprendeu a antecipar |
| `drives.json` | Energia, estimulação e carência |
| `protest.json`, `sad_protest.json` | Insatisfação e tristeza |
| `castigo.json` | Fugas do cantinho, rancor e receio |
| `.migrado` | Só existe se a memória veio da versão antiga: quando migrou e o hash de cada arquivo |

Quem usou uma versão antiga (arquivos soltos em `memory/`) tem a memória migrada sozinha na primeira
abertura. Os originais não são apagados: ficam em `memory/legado/<pet>/`. Se a migração não puder ser
concluída (por exemplo, um arquivo já existe com outro conteúdo), nada é sobrescrito, ele continua usando
os arquivos antigos e avisa no ícone da bandeja.

## Como apagar

- Na tela de configurações, **Apagar histórico** apaga a rotina (`timeline.csv`), inclusive o minuto que
  ainda estava na memória.
- **Apagar todos os dados do Pestinha** apaga a pasta `memory/` inteira, com a memória de todos os personagens (pede confirmação, desliga o início com o Windows e fecha o programa). Se algum arquivo não puder ser apagado, ele avisa quais foram antes de fechar.
- Você também pode apagar a pasta `memory/` manualmente, com o programa fechado.

## Fora da pasta de dados

- **Voz natural** (só se você instalar): a pasta `voz_natural/`, ao lado do programa, com o PyTorch e o modelo
  (uns 4,5 GB). Não tem nenhum dado seu. **Apagar todos os dados** não apaga essa pasta; use **Remover** na
  tela da voz natural.
- **Falar os bilhetes e cartazes** (desligado por padrão): o texto do post-it ou do cartaz vai para a voz do
  sistema (`say`) ou para o modelo, os dois no seu computador.
- **Frases com IA** (só se você instalar): a pasta `ia_local/`, ao lado do programa, com o llama.cpp e o modelo
  (uns 1,3 GB). Não tem nenhum dado seu. O pedido ao modelo leva o que o pet sente, a categoria do programa
  em primeiro plano (programando, jogando...; nunca o nome nem o título da janela), a parte do dia e frases
  do pet. Fica no seu computador e não é gravado; o log anota só quanto tempo levou (a frase, só no Modo teste).
- **Espiar a tela e comentar** (desligado por padrão, em teste): de vez em quando, ele tira um print do monitor
  principal, reduz e entrega à IA local, no seu computador, que escreve um comentário. O print fica num arquivo
  temporário, que só o seu usuário lê, e é **apagado logo depois que o modelo olha**, dê certo ou não. Nunca é
  gravado na pasta de dados nem enviado para lugar nenhum. O pedido ao modelo diz para não copiar textos, nomes,
  números, e-mails nem senhas da tela, mas o comentário pode citar algo que aparece nela. No macOS, precisa da
  permissão de Gravação de Tela, que ele só pede quando você liga a opção ou clica em **Espiar a tela e
  comentar (IA)** no menu. **Exceção, só no Modo teste:** uma cópia do último print que a IA olhou fica em
  `logs/ultima_espiada.png`, na pasta de dados, para você conferir a captura. Ela é substituída a cada espiada
  e apagada quando o Modo teste é desligado (e por **Apagar todos os dados**).

- **Abrir ao entrar no Windows** (desligado por padrão) grava uma entrada em
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, só para o seu usuário.
- Um arquivo de trava na pasta temporária do sistema impede abrir duas cópias. Não contém dados seus além do
  número do processo e do nome do computador.

## Controle

- Cada permissão pode ser desligada na tela de configurações; desligar uma permissão também recolhe o que
  já estava na tela.
- O atalho **Ctrl + Alt + Shift + B** desliga tudo na hora, e ele continua desligado até você religar.
