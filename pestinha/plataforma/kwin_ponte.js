// Ponte do KWin (Plasma 6): manda para o Pestinha, por DBus, o que o Wayland não deixa um programa ver.
// Só geometria, pid e estado das janelas; nunca títulos. Carregado e descarregado por kwin.py.

const SERVICO = "io.github.pestinha", CAMINHO = "/ponte", INTERFACE = "io.github.pestinha.Ponte";

function naMesa(w) {
    return w.onAllDesktops || w.desktops.indexOf(workspace.currentDesktop) >= 0;
}

function resumo(w) {
    const g = w.frameGeometry, m = workspace.clientArea(KWin.MaximizeArea, w);
    return {
        id: String(w.internalId), pid: w.pid, x: g.x, y: g.y, w: g.width, h: g.height,
        cheia: w.fullScreen, max: g.width >= m.width && g.height >= m.height,
    };
}

function enviar() {
    const janelas = workspace.stackingOrder
        .filter(w => w.normalWindow && !w.minimized && naMesa(w))
        .reverse()                                       // de cima para baixo, como os outros sistemas
        .map(resumo);
    const ativa = workspace.activeWindow;
    callDBus(SERVICO, CAMINHO, INTERFACE, "estado",
             JSON.stringify({janelas: janelas, ativa: ativa ? resumo(ativa) : null}));
}

let meuPid = null;

function foraDaBarra(w) {
    // na hora em que a janela aparece: o pedido do app (wmctrl) chega tarde e ela pisca na barra
    if (w.pid === meuPid) {
        w.skipTaskbar = true;
        w.skipPager = true;
    }
}

function observar(w) {
    w.frameGeometryChanged.connect(enviar);
    w.fullScreenChanged.connect(enviar);
    w.minimizedChanged.connect(enviar);
}

workspace.windowList().forEach(observar);
workspace.windowAdded.connect(w => { foraDaBarra(w); observar(w); enviar(); });
workspace.windowRemoved.connect(enviar);
workspace.windowActivated.connect(enviar);
workspace.currentDesktopChanged.connect(enviar);
workspace.cursorPosChanged.connect(() => {
    const p = workspace.cursorPos;
    callDBus(SERVICO, CAMINHO, INTERFACE, "cursor", JSON.stringify([p.x, p.y]));   // texto: o tipo do número no DBus não importa
});
registerShortcut("Pestinha: mostrar", "Pestinha: mostrar ou esconder o pet", "Ctrl+Alt+Shift+B",
                 () => callDBus(SERVICO, CAMINHO, INTERFACE, "atalho"));
callDBus(SERVICO, CAMINHO, INTERFACE, "pid", pid => {
    meuPid = pid;
    workspace.windowList().forEach(foraDaBarra);
});
enviar();
