"""Visual layout for Oracle's native desktop workspace."""
import tkinter as tk
from tkinter import ttk

BG, SIDE, PANEL = "#0C111B", "#101723", "#151F2E"
TEXT, MUTED, ACCENT, LINE = "#E6EDF7", "#94A3B8", "#75E1D2", "#263246"


def label(parent, text, size=10, color=TEXT, bold=False, **kw):
    return tk.Label(parent, text=text, fg=color, bg=parent.cget("bg"),
                    font=("Segoe UI", size, "bold" if bold else "normal"), **kw)


def button(ui, parent, text, command, primary=False, anchor="center"):
    bg = ACCENT if primary else PANEL
    widget = tk.Button(parent, text=text, command=command, font=("Segoe UI", 10),
                       bg=bg, fg=BG if primary else TEXT, activebackground="#263D50",
                       activeforeground=TEXT, disabledforeground="#677991", relief="flat",
                       bd=0, padx=13, pady=10, cursor="hand2", anchor=anchor,
                       highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)
    widget.bind("<Enter>", lambda _: widget.configure(bg="#243448") if not primary and widget.cget("state") != "disabled" else None)
    widget.bind("<Leave>", lambda _: widget.configure(bg=bg))
    ui._buttons.append(widget)
    return widget


def build(ui):
    root = tk.Tk()
    ui._root = root
    root.title("Oracle · Your personal assistant")
    root.geometry("1180x820")
    root.minsize(880, 680)
    root.configure(bg=BG)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(0, weight=1)
    ui._buttons = []
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Oracle.Vertical.TScrollbar", background=LINE, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, lightcolor=LINE, darkcolor=LINE)

    side = tk.Frame(root, bg=SIDE, width=208, padx=18, pady=20)
    side.grid(row=0, column=0, sticky="nsew")
    side.pack_propagate(False)
    brand = tk.Frame(side, bg=SIDE)
    brand.pack(fill="x", pady=(0, 5))
    logo = tk.Canvas(brand, width=32, height=36, bg=SIDE, highlightthickness=0)
    logo.pack(side="left", padx=(0, 10))
    logo.create_oval(4, 5, 27, 28, outline=ACCENT, width=2)
    logo.create_oval(11, 12, 20, 21, fill=ACCENT, outline="")
    label(brand, "oracle", 23, bold=True).pack(side="left")
    label(side, "PERSONAL WORKSPACE", 8, MUTED).pack(anchor="w", pady=(0, 22))
    button(ui, side, "+   Clear conversation", ui._clear_chat).pack(fill="x", pady=(0, 18))
    label(side, "WORKSPACE", 8, MUTED, True).pack(anchor="w", pady=(0, 12))
    for title, action in (
        ("Conversation", lambda: ui._entry.focus_set()),
        ("MyMoney", ui._open_finance),
        ("Capabilities", lambda: ui._quick_prompt("help")),
        ("Devices", lambda: ui._quick_prompt("list devices")),
        ("Preferences", lambda: ui._quick_prompt("show preferences")),
    ):
        item = button(ui, side, title, action, anchor="w")
        item.configure(pady=7)
        item.pack(fill="x", pady=3)
        if title == "Conversation":
            item.configure(fg=ACCENT)
    label(side, "AUTOMATION", 8, MUTED, True).pack(anchor="w", pady=(18, 10))
    button(ui, side, "Start device monitor", lambda: ui._quick_prompt("start monitoring"), anchor="w").pack(fill="x", pady=4)
    button(ui, side, "Stop device monitor", lambda: ui._quick_prompt("stop monitoring"), anchor="w").pack(fill="x", pady=4)
    bottom = tk.Frame(side, bg=SIDE)
    bottom.pack(side="bottom", fill="x")
    tk.Frame(bottom, bg=LINE, height=1).pack(fill="x", pady=14)
    ui._connection_var = tk.StringVar(value="Connections not checked")
    tk.Label(bottom, textvariable=ui._connection_var, fg=MUTED, bg=SIDE,
             font=("Segoe UI", 9), wraplength=165, justify="left").pack(anchor="w", pady=(0, 12))
    button(ui, bottom, "Connections & privacy", ui._connections, anchor="w").pack(fill="x")

    main = tk.Frame(root, bg=BG, padx=30, pady=22)
    main.grid(row=0, column=1, sticky="nsew")
    main.grid_columnconfigure(0, weight=1)
    main.grid_rowconfigure(2, weight=1)
    header = tk.Frame(main, bg=BG)
    header.grid(row=0, column=0, sticky="ew")
    label(header, "Your assistant", 17, bold=True).pack(side="left")
    label(header, "●  ON DEMAND", 9, ACCENT).pack(side="right")
    label(main, "Think clearly. Get things done.", 10, MUTED).grid(row=1, column=0, sticky="w", pady=(5, 18))
    content = tk.Frame(main, bg=BG)
    content.grid(row=2, column=0, sticky="nsew")
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(0, weight=1)
    ui._welcome = tk.Frame(content, bg=BG)
    ui._welcome.grid(row=0, column=0, sticky="nsew")
    ui._welcome.grid_columnconfigure(0, weight=1)
    ui._welcome.grid_rowconfigure(0, weight=1)
    hero = tk.Frame(ui._welcome, bg=BG)
    hero.grid(row=0, column=0)
    orb = tk.Canvas(hero, width=132, height=94, bg=BG, highlightthickness=0)
    orb.pack()
    for r, color in ((49, "#172B38"), (39, "#24515A"), (27, ACCENT)):
        orb.create_oval(66-r, 57-r, 66+r, 57+r, outline=color, width=2)
    orb.create_arc(17, 8, 115, 106, start=30, extent=95, outline=ACCENT, style="arc", width=2)
    orb.create_oval(59, 50, 73, 64, fill=ACCENT, outline="")
    orb.scale("all", 66, 0, 0.8, 0.8)
    hero_title = label(hero, "What would you like to do?", 23, bold=True)
    hero_title.pack(pady=(6, 6))
    cards = tk.Frame(ui._welcome, bg=BG)
    cards.grid(row=1, column=0, sticky="ew", pady=(20, 26))
    cards.grid_columnconfigure((0, 1), weight=1, uniform="cards")
    for index, (title, detail, prompt) in enumerate((
        ("01   Plan my day", "Turn priorities into a practical plan", "Help me plan my day. Ask about my priorities first."),
        ("02   Explore an idea", "Find clarity, options and next steps", "Help me think through an idea."),
        ("03   Discover Oracle", "Explore what your assistant can do", "help"),
        ("04   Connected devices", "See devices and their current state", "list devices"),
    )):
        card = button(ui, cards, title + "\n" + detail, lambda p=prompt: ui._draft(p), anchor="w")
        card.configure(justify="left", pady=14, wraplength=240)
        card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 8) if index % 2 == 0 else (8, 0), pady=6)
    ui._chat = tk.Frame(content, bg=BG)
    ui._chat.grid_columnconfigure(0, weight=1)
    ui._chat.grid_rowconfigure(0, weight=1)
    ui._output = tk.Text(ui._chat, wrap="word", bg=BG, fg=TEXT, bd=0, relief="flat",
                         highlightthickness=0, padx=12, pady=14, font=("Segoe UI", 11),
                         spacing1=5, spacing3=12, state="disabled", width=30)
    ui._output.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(ui._chat, orient="vertical", command=ui._output.yview, style="Oracle.Vertical.TScrollbar")
    scroll.grid(row=0, column=1, sticky="ns")
    ui._output.configure(yscrollcommand=scroll.set)
    ui._output.tag_configure("user", foreground=TEXT, font=("Segoe UI", 10, "bold"), spacing1=18)
    ui._output.tag_configure("oracle", foreground=ACCENT, font=("Segoe UI", 10, "bold"), spacing1=18)

    composer = tk.Frame(main, bg=PANEL, highlightbackground=LINE, highlightthickness=1, padx=16, pady=14)
    composer.grid(row=3, column=0, sticky="ew")
    label(composer, "MESSAGE ORACLE", 8, MUTED, True).pack(anchor="w", pady=(0, 10))
    ui._entry = tk.Entry(composer, bg=PANEL, fg=TEXT, insertbackground=ACCENT,
                         font=("Segoe UI", 12), relief="flat", bd=0)
    ui._entry.pack(fill="x", ipady=7)
    ui._entry.bind("<Return>", lambda _: ui._submit())
    toolbar = tk.Frame(composer, bg=PANEL)
    toolbar.pack(fill="x", pady=(12, 0))
    for title, action in (("Microphone", "listen"), ("Screen", "screen"), ("Read aloud", "speak")):
        button(ui, toolbar, title, lambda a=action: ui._media_action(a)).pack(side="left", padx=(0, 6))
    ui._send = button(ui, toolbar, "Send  ↑", ui._submit, primary=True)
    ui._send.pack(side="right")
    footer = tk.Frame(main, bg=BG)
    footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
    ui._status_var = tk.StringVar(value="Ready when you are")
    tk.Label(footer, textvariable=ui._status_var, fg=MUTED, bg=BG, font=("Segoe UI", 9), anchor="w").pack(side="left")
    label(footer, "Enter to send  ·  Ctrl+L to focus", 8, MUTED).pack(side="right")
    root.bind("<Control-l>", lambda _: ui._entry.focus_set())
    root.protocol("WM_DELETE_WINDOW", ui._close)
    ui._entry.focus_set()
    return root
