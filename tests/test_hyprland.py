"""
Backend Hyprland: as funções puras (JSON do hyprctl -> retângulos/nomes) são testadas
com saídas de exemplo, em qualquer sistema; o caminho real só roda no Hyprland.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pestinha.plataforma import hyprland  # noqa: E402

FUNCOES = ["ocioso_segundos", "processo_ativo", "retangulo_ativo", "tela_cheia",
           "janelas_visiveis", "sem_foco_nativo", "iniciar_atalho"]


def _cliente(address="0x1234", pid=2222, at=(6, 46), size=(1588, 848),
             focus=0, fullscreen=0, mapped=True, classe="kitty", titulo="zsh"):
    return {"address": address, "pid": pid, "at": list(at), "size": list(size),
            "focusHistoryID": focus, "fullscreen": fullscreen, "mapped": mapped,
            "class": classe, "title": titulo, "initialClass": classe}


def test_expoe_as_mesmas_funcoes_dos_outros_backends():
    for nome in FUNCOES:
        assert callable(getattr(hyprland, nome)), nome
    assert callable(hyprland.mover_janela)
    assert callable(hyprland.configurar_janela)


def test_retangulo_de_cliente():
    assert hyprland.retangulo_de(_cliente(at=(6, 46), size=(1588, 848))) == (6, 46, 1594, 894)
    assert hyprland.retangulo_de({}) is None
    assert hyprland.retangulo_de({"at": [1], "size": [2]}) is None


def test_parse_clientes_ordena_por_foco_e_pula_o_proprio_e_as_pequenas():
    clientes = [
        _cliente(address="0xaaaa", pid=9999, focus=2),                                  # fundo
        _cliente(address="0xbbbb", pid=4444, focus=0),                                  # o próprio pet
        _cliente(address="0xcccc", pid=3333, focus=1, size=(80, 40)),                   # pequena
        _cliente(address="0xdddd", pid=5555, focus=3, mapped=False),                    # sem mapa
        _cliente(address="0xeeee", pid=6666, focus=1, at=(0, 0), size=(1920, 1080),
                 fullscreen=1),                                                        # frente
    ]
    achadas = hyprland.parse_clientes(clientes, meu_pid=4444)
    assert achadas == [
        (0xeeee, (0, 0, 1920, 1080), True),
        (0xaaaa, (6, 46, 1594, 894), False),
    ]


def test_parse_clientes_nao_guarda_titulo():
    achadas = hyprland.parse_clientes([_cliente(titulo="Senha do banco")], meu_pid=1)
    assert "Senha" not in repr(achadas)
    assert achadas == [(0x1234, (6, 46, 1594, 894), False)]


def test_nome_do_processo_usa_a_classe_quando_nao_acha_o_pid():
    assert hyprland.nome_do_processo(_cliente(pid=999999, classe="kitty")) == "kitty"
    assert hyprland.nome_do_processo({"address": "0x1"}) == "unknown"


def test_cobre_monitor():
    monitores = [{"x": 0, "y": 0, "width": 1920, "height": 1080}]
    assert hyprland.cobre_monitor((0, 0, 1920, 1080), monitores) is True
    assert hyprland.cobre_monitor((6, 46, 1594, 894), monitores) is False
    assert hyprland.cobre_monitor(None, monitores) is False
    assert hyprland.cobre_monitor((0, 0, 1920, 1080), []) is False


def test_comando_move_usa_a_sintaxe_lua_do_dispatcher():
    comando = hyprland._comando_move("0x1234abcd", 300, 250)
    assert comando == ('hl.dsp.window.move({x=300, y=250, relative=false, '
                       'window="address:0x1234abcd"})')


def test_ocioso_no_hyprland_e_zero():
    # o compositor não expõe o tempo ocioso: o pet fica como "sempre ativo"
    assert hyprland.ocioso_segundos() == 0.0
