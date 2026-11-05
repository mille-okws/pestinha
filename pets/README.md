# Pets

Um pet são duas coisas com o mesmo nome:

- `<pet>.json`: quem ele é (nome, semente da rede, temperamento). É o que faz o pet existir e aparecer
  como opção. Só os `.json` desta pasta contam; uma pasta de memória antiga não cria personagem.
- `<pet>/`: o conteúdo dele (frases, cartazes, memes e, se quiser, imagens próprias).

## `<pet>.json`

| Campo | Para que serve |
|---|---|
| `nome` | Nome que aparece nos textos. |
| `seed` | Semente da rede (inteiro ≥ 0): outra semente é outro "indivíduo" com a mesma estrutura. |
| `brincadeira` | Pesos de cada jeito de brincar: `bola` (chuta), `arremesso` (joga no cursor), `postit` (cola post-its). Peso 0 desliga. |
| `temperamento` | Ganhos que multiplicam estímulos antes de chegarem aos interneurônios. Ex.: `"DISMISS->FRUSTRATION": 1.3` deixa o pet mais irritado quando você dispensa coisas. Os nomes estão em [docs/REDE_NEURAL.md](../docs/REDE_NEURAL.md). |
| `reacao_notebook` | `"bravo"` ou `"triste"`: o que ele sente quando arrancam o notebook dele. |
| `aparencia` | Opcional. Cores `#rrggbb` de `moldura`, `casca`, `tela`, `olho` e `brilho`, e `acessorios` com a cor de cada um: `{"oculos": "#f2f2f2", "gravata": "#b3261e"}`. Sem o campo, o visual original. |

Campos com tipo errado são ignorados e ficam com o valor padrão (não derrubam o app).

## `<pet>/`

Pode editar com ele aberto: ele relê os textos e procura imagens novas sozinho.

| Arquivo ou pasta | O que é |
|---|---|
| `memes/<emoção>/` | Imagens (.png .jpg .gif .webp .bmp) que ele traz com aquela emoção: `feliz`, `contente`, `observando`, `curioso` (arrastadas pela tela), `bravo` (pequenas, num cantinho), `triste`, `assustado`, `dramatico`. Se a pasta da emoção estiver vazia, usa um meme de outra emoção **do mesmo pet**. |
| `memes/trabalhando/` | Memes de quando você programa e ele não está sentado no notebook. |
| `recadinhos_ide.txt`, `recadinhos_notebook.txt` | Opcionais: ativam comentários ao entrar numa IDE ou enquanto o pet usa o notebook. Uma frase por linha. Sem o arquivo correspondente, não há reação contextual. |
| `memes/notebook/` | Memes para os comentários enquanto o pet está sentado. Os de entrada na IDE usam `memes/trabalhando/`. |
| `recadinhos.txt` | Uma frase por linha, sorteada para os post-its. `#` é comentário. |
| `recadinhos_tristes.txt` | Bilhetes que ele cola quando está triste. |
| `cartazes.txt` | Cartazes por seção: `[reclamacao]`, `[manifestacao]`, `[greve]`, `[revolucao]`, `[acordo]`, `[desistiu]`, `[saudade]`, `[chorando]`, `[abandonado]`, `[volto]`, e no cantinho do castigo `[castigo]` e `[xingamento]`. |
| `bolinha_tenis.png`, `bolinha_papel.png`, `notebook.png` | Opcionais: se existirem aqui, valem no lugar dos de `assets/comum/`. |

O que faltar na pasta do pet é procurado em `assets/comum/`. Se também não estiver lá, ele usa frases
neutras (cartazes) ou simplesmente não faz aquela travessura (memes, post-its). **Nunca** usa o conteúdo
de outro pet.

## Personagens que já existem

- **Bryan** (`bryan.json`, `bryan/`): o original.
- **Eddie** (`eddie.json`, `eddie/`): colega dev debochado, de óculos, olhos verde-menta e moldura lilás.
  IDE e digitação aumentam mais o foco, favorecendo o notebook. Tem 22 memes em pixel art gerados
  com imagegen integrado (prompts em `eddie/memes/prompts.json`), além de recadinhos e cartazes próprios.
  Seu brinquedo é um cubo mágico com fundo transparente, salvo em `eddie/bolinha_tenis.png`
  para substituir a bola apenas nele (prompt em `eddie/cubo_magico.prompt.txt`).
  `ferramentas/gerar_memes_eddie.py` valida as imagens e exporta as frases; não sobrescreve as artes.
  Não lê código nem executa
  as "correções" das piadas. Para os comentários, ligue Travessuras e memes e/ou bilhetes.
- **Jorge** (`jorge.json`, `jorge/`): coach trambiqueiro. Mais insistente quando ignorado, muito animado
  com atenção, desesperado quando dispensam as coisas dele e quase nunca triste. O panfleto que ele atira
  (`jorge/bolinha_papel.png`) é desenhado por `ferramentas/gerar_panfleto.py`. Moldura e olhos dourados
  e gravata vermelha. Memes felizes, contentes, curiosos e bravos próprios em `jorge/memes/feliz/`, `contente/`, `curioso/` e `bravo/`; as outras emoções ainda sem memes.

## Criar outro pet

1. Copie `bryan.json` com o novo nome (letras minúsculas, números, `-` ou `_`), por exemplo `jorge.json`,
   e mude os valores.
2. Crie a pasta `jorge/` com as frases e memes dele. Pode começar vazia: ele funciona com o neutro.
3. Escolha o personagem em Configurações. A troca vale na próxima vez que abrir.
4. A memória dele fica separada, em `memory/pets/jorge/`.
5. Confira se os cartazes cabem nas placas: `python ferramentas/medir_cartazes.py jorge`.

Cada chave do `temperamento` precisa ser uma ligação que existe (`SENSOR->INTERNEURÔNIO` ou só o
interneurônio); `tests/test_jorge.py` confere isso para todos os pets.

Os comentários contextuais são regras explícitas, separadas das travessuras sorteadas pela rede.
Há pelo menos 90 segundos entre eles e uma tentativa a cada 120 segundos no notebook. Trocar
rapidamente de app não cria uma fila; eventos bloqueados pelas permissões são descartados.
Textos e imagens continuam isolados por personagem. Os intervalos ficam em `pestinha/ajustes.py`.
