"""MyMoney workspace inside Oracle. No web server and no remote data access."""
from datetime import date
from decimal import Decimal
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from app.finance import FinanceStore, money, pence
from app.ui_layout import BG, PANEL, TEXT, MUTED, ACCENT, label


class FinanceWindow:
    def __init__(self, parent=None, store=None):
        self.store = store or FinanceStore()
        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Oracle · MyMoney")
        self.window.geometry("1100x800")
        self.window.minsize(850, 650)
        self.window.configure(bg=BG)
        header = tk.Frame(self.window, bg=BG, padx=24, pady=12)
        header.pack(fill="x")
        label(header, "MyMoney", 20, bold=True).pack(side="left")
        label(header, "PRIVATE · LOCAL RECORDS · GBP", 10, ACCENT).pack(side="right")
        label(self.window, "Plan your spending. Protect your priorities.", 10, MUTED).pack(anchor="w", padx=24)
        label(self.window, "Local manual records · Finance data is not sent to Oracle's LLM.", 9, MUTED).pack(side='bottom', pady=8)
        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure("Money.Treeview", rowheight=29, background=PANEL, foreground=TEXT, fieldbackground=PANEL)
        style.configure("Money.Treeview.Heading", background=BG, foreground=TEXT)
        style.configure("Money.TNotebook", background=BG, borderwidth=0)
        style.configure("Money.TNotebook.Tab", background=PANEL, foreground=TEXT, padding=(10, 8))
        style.map("Money.TNotebook.Tab", background=[('selected', '#263246')], foreground=[('selected', ACCENT)])
        self.notebook = ttk.Notebook(self.window, style="Money.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=24, pady=18)
        self.tabs = {}
        for title in ("Overview", "Transactions", "Bills & income", "Savings pots", "Forecast & settings"):
            page = tk.Frame(self.notebook, bg=BG, padx=16, pady=16)
            self.notebook.add(page, text=title)
            self.tabs[title] = page
        self._overview()
        self._transactions()
        self._schedules()
        self._pots()
        self._forecast()
        self.refresh()

    def button(self, parent, title, callback):
        widget = tk.Button(parent, text=title, command=lambda: self.guard(callback), bg=PANEL,
                           fg=TEXT, activebackground=ACCENT, relief="flat", padx=12, pady=8)
        widget.pack(side="left", padx=(0, 8), pady=8)
        return widget

    def guard(self, callback):
        try:
            callback()
        except (ValueError, sqlite3.Error, OSError) as exc:
            messagebox.showerror("MyMoney", str(exc), parent=self.window)

    def form(self, title, fields, save):
        """Fields: (key, label, default, choices-or-None)."""
        dialog = tk.Toplevel(self.window)
        dialog.title(title)
        dialog.configure(bg=BG)
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.resizable(False, False)
        values = {}
        for index, (key, caption, default, choices) in enumerate(fields):
            label(dialog, caption).grid(row=index, column=0, sticky="w", padx=18, pady=9)
            variable = tk.StringVar(value=str(default))
            values[key] = variable
            field = ttk.Combobox(dialog, textvariable=variable, values=choices, state="readonly") if choices else ttk.Entry(dialog, textvariable=variable, width=32)
            field.grid(row=index, column=1, padx=18, pady=9)
        def submit():
            def action():
                save({key: variable.get().strip() for key, variable in values.items()})
                dialog.destroy()
                self.refresh()
            self.guard(action)
        tk.Button(dialog, text="Save", command=submit, bg=ACCENT, padx=18).grid(row=len(fields), column=1, sticky="e", padx=18, pady=18)
        tk.Button(dialog, text="Cancel", command=dialog.destroy).grid(row=len(fields), column=0, padx=18, pady=18)

    def table(self, parent, columns, height=12):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True, pady=8)
        tree = ttk.Treeview(frame, columns=columns, show="headings", style="Money.Treeview", height=height, selectmode="browse")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, minwidth=65)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    def fill(self, tree, rows):
        tree.delete(*tree.get_children())
        for identity, values in rows:
            tree.insert("", "end", iid=str(identity), values=values)

    def selected(self, tree):
        selected = tree.selection()
        if not selected:
            raise ValueError("Select a row first.")
        return selected[0]

    def _overview(self):
        page = self.tabs['Overview']
        self.totals = tk.StringVar()
        totals = tk.Label(page, textvariable=self.totals, bg=PANEL, fg=TEXT, font=("Segoe UI", 13), justify="left", anchor='w', padx=16, pady=12)
        totals.pack(fill="x")
        totals.bind('<Configure>', lambda event: totals.configure(wraplength=max(200,event.width-32)))
        self.chart = tk.Canvas(page, height=115, bg=BG, highlightthickness=0)
        self.chart.pack(fill="x", pady=12)
        self.chart.bind("<Configure>", lambda _: self.draw_budget())
        self.notices = tk.Text(page, height=3, wrap="word", bg=PANEL, fg=TEXT, relief="flat", padx=12, pady=10, font=('Segoe UI',10))
        self.notices.pack(fill="x")
        bar = tk.Frame(page, bg=BG); bar.pack(fill="x")
        self.button(bar, "Set balance", self.reconcile)
        self.button(bar, "Set payday & limits", self.settings)
        self.button(bar, "Refresh", self.refresh)
        label(page, "Upcoming bills and expected income · select one and record it when paid / received", 10, MUTED).pack(anchor="w")
        action_bar = tk.Frame(page, bg=BG)
        action_bar.pack(side='bottom', fill='x')
        self.button(action_bar, "Record selected payment / receipt", self.settle)
        self.upcoming = self.table(page, ("Due", "Name", "Type", "Amount", "Estimate"), height=4)

    def _transactions(self):
        page = self.tabs['Transactions']
        label(page, "Actual money in and out", 18, bold=True).pack(anchor="w")
        label(page, "For a scheduled bill or salary, use Record payment / receipt on Overview to avoid duplicates.", 10, MUTED).pack(anchor="w")
        bar = tk.Frame(page, bg=BG); bar.pack(fill="x")
        self.button(bar, "Add transaction", self.transaction)
        self.button(bar, "Edit selected", lambda: self.transaction(int(self.selected(self.tx))))
        self.button(bar, "Delete selected", self.delete_transaction)
        self.tx = self.table(page, ("Date", "Name", "Amount", "Category", "Linked"))

    def _schedules(self):
        page = self.tabs['Bills & income']
        label(page, "Plan commitments and expected income", 18, bold=True).pack(anchor="w")
        label(page, "Start date is the first UNPAID occurrence. Expected income never changes your real balance.", 10, MUTED).pack(anchor="w")
        bar = tk.Frame(page, bg=BG); bar.pack(fill="x")
        self.button(bar, "Add bill / income", self.schedule)
        self.button(bar, "Stop selected schedule", self.stop_schedule)
        self.schedules = self.table(page, ("Name", "Type", "Amount", "First due", "Frequency", "Category", "Estimate"))

    def _pots(self):
        page = self.tabs['Savings pots']
        label(page, "Give your savings a purpose", 18, bold=True).pack(anchor="w")
        label(page, "Virtual reservations inside your bank balance, not expenses or separate bank accounts.", 10, MUTED).pack(anchor="w")
        bar = tk.Frame(page, bg=BG); bar.pack(fill="x")
        self.button(bar, "New savings pot", self.pot)
        self.button(bar, "Allocate / release", self.move_pot)
        self.pots = self.table(page, ("Goal", "Reserved", "Target", "Progress", "Target date"), height=6)
        label(page, "Allocation history", 12, MUTED).pack(anchor="w")
        self.movements = self.table(page, ("Date", "Pot", "Movement"), height=5)

    def _forecast(self):
        page = self.tabs['Forecast & settings']
        bar = tk.Frame(page, bg=BG); bar.pack(fill="x")
        self.button(bar, "Payday & thresholds", self.settings)
        self.button(bar, "Reconcile balance", self.reconcile)
        self.button(bar, "Private database backup", self.backup)
        label(page, "90-day forecast · scheduled cashflows only; excludes future discretionary spending.", 11, MUTED).pack(anchor="w")
        label(page, "Overdue bills assumed due now; overdue income excluded. Bills precede income on the same day.", 10, MUTED).pack(anchor="w")
        self.forecast_canvas = tk.Canvas(page, height=180, bg=PANEL, highlightthickness=0)
        self.forecast_canvas.pack(fill="x", pady=12)
        self.forecast_canvas.bind("<Configure>", lambda _: self.draw_forecast())
        self.forecast_table = self.table(page, ("Date", "Closing balance", "Low before income", "Protected funds", "Shortfall"), height=8)

    def refresh(self):
        self.summary = s = self.store.summary()
        daily = money(s['daily']) if s['daily'] is not None else "Set future payday"
        weekly = money(s['weekly']) if s['weekly'] is not None else "Paused"
        status = s['risk'].upper() if s['configured'] else "SETUP NEEDED"
        self.totals.set(f"Bank balance  {money(s['balance'])}     Available after reserves  {money(s['spendable'])}\n"
                        f"Daily  {daily}     Next 7 days  {weekly}     {status}")
        self.notices.configure(state="normal")
        self.notices.delete("1.0", "end")
        self.notices.insert("end", "\n".join(s['notices']) or "Your recorded plan covers commitments and reserves. Unrecorded spending changes this estimate.")
        self.notices.configure(state="disabled")
        self.fill(self.upcoming, [(f"{r['id']}|{r['due']}", (r['due'], r['name'], r['kind'], money(r['amount']), 'Yes' if r['estimated'] else 'No')) for r in s['pending']])
        self.fill(self.tx, [(r['id'], (r['day'], r['name'], money(r['amount']), r['category'], r['due'] or '')) for r in self.store.transactions()])
        self.fill(self.schedules, [(r['id'], (r['name'], r['kind'], money(r['amount']), r['start'], r['frequency'], r['category'], 'Yes' if r['estimated'] else 'No')) for r in self.store.schedules()])
        self.fill(self.pots, [(r['id'], (r['name'], money(r['reserved']), money(r['target']), f"{r['reserved'] * 100 // r['target']}%", r['target_date'] or '')) for r in self.store.pots()])
        self.fill(self.movements, [(r['id'], (r['day'], r['name'], money(r['amount']))) for r in self.store.movements()])
        self.projection = self.store.forecast()
        self.fill(self.forecast_table, [(r['day'], (r['day'], money(r['balance']), money(r['low']), money(r['protected']), money(r['shortfall']))) for r in self.projection])
        self.draw_budget(); self.draw_forecast()

    def draw_budget(self):
        if not hasattr(self, 'summary'):
            return
        self.chart.delete('all')
        s = self.summary
        segments = [('Bills', s['commitments'], '#E9AA65'), ('Savings', s['reserved'], '#A89BEE'), ('Buffer', s['buffer'], '#7398D4'), ('Spendable', s['spendable'], ACCENT)]
        total = sum(value for _, value, _ in segments) or 1
        width = max(300, self.chart.winfo_width()) - 4
        x = 2
        for i, (name, value, color) in enumerate(segments):
            end = x + width * value / total
            self.chart.create_rectangle(x, 12, end, 40, fill=color, outline='')
            self.chart.create_text(4 + i * width / 4, 62, anchor='nw', text=f"{name}\n{money(value)}", fill=color, font=('Segoe UI', 10))
            x = end

    def draw_forecast(self):
        if not hasattr(self, 'projection'):
            return
        canvas = self.forecast_canvas; canvas.delete('all')
        rows = self.projection
        width = max(300, canvas.winfo_width()) - 100
        lo = min(0, min(r['low'] for r in rows)); hi = max(1, max(max(r['balance'], r['protected']) for r in rows))
        y = lambda amount: 140 - (amount-lo) / (hi-lo) * 110
        for field, color in (('balance', ACCENT), ('protected', '#E9AA65')):
            coords = [coordinate for i, r in enumerate(rows) for coordinate in (85+i*width/(len(rows)-1), y(r[field]))]
            canvas.create_line(*coords, fill=color, width=2)
        canvas.create_text(8, 20, text=money(hi), anchor='nw', fill=MUTED)
        canvas.create_text(8, 130, text=money(lo), anchor='nw', fill=MUTED)
        canvas.create_text(85, 160, text="Today → 90 days    • Cash (teal)    • Protected reserves (amber)", anchor='w', fill=TEXT)

    def settings(self):
        s = self.store.settings()
        self.form("Payday & limits", [('payday','Next payday YYYY-MM-DD',s['payday'] or '',None), ('buffer','Safety buffer (£)',Decimal(s['buffer'])/100,None), ('warning','Caution threshold (£)',Decimal(s['warning'])/100,None)],
                  lambda v: self.store.configure(v['payday'],pence(v['buffer']),pence(v['warning'])))

    def reconcile(self):
        self.form("Actual bank balance", [('balance','Actual balance (£)',Decimal(self.store.balance())/100,None)], lambda v: self.store.reconcile(pence(v['balance'])))

    def transaction(self, identity=None):
        row = next((r for r in self.store.transactions() if r['id']==identity), {})
        self.form("Record actual transaction", [('name','Description',row.get('name',''),None), ('amount','Signed amount (£; expense is negative)',Decimal(row.get('amount',0))/100,None), ('day','Date YYYY-MM-DD',row.get('day',date.today().isoformat()),None), ('category','Category',row.get('category','General'),None)],
                  lambda v:self.store.transaction(v['name'],pence(v['amount']),v['day'],v['category'],identity))

    def delete_transaction(self):
        identity = int(self.selected(self.tx))
        if messagebox.askyesno("Delete transaction", "Delete this record? A linked bill or income occurrence becomes unpaid again.", parent=self.window):
            self.store.delete_transaction(identity); self.refresh()

    def schedule(self):
        self.form("New bill or expected income", [('name','Name','',None), ('kind','Type','bill',['bill','income']), ('amount','Positive amount (£)','',None), ('start','First unpaid due date YYYY-MM-DD',date.today().isoformat(),None), ('frequency','Frequency','monthly',['once','weekly','monthly','yearly']), ('category','Category','General',None), ('estimated','Estimated amount?','No',['No','Yes'])],
                  lambda v:self.store.add_schedule(v['name'],pence(v['amount']),v['kind'],v['start'],v['frequency'],v['category'],v['estimated']=='Yes'))

    def stop_schedule(self):
        identity = int(self.selected(self.schedules))
        if messagebox.askyesno("Stop schedule", "Remove ALL unpaid occurrences of this schedule from the plan? Recorded transactions remain. To change an amount, stop this schedule and add a replacement starting on the next unpaid date.", parent=self.window):
            self.store.stop_schedule(identity); self.refresh()

    def settle(self):
        identity, due = self.selected(self.upcoming).split('|')
        if messagebox.askyesno("Record actual payment", "Has this amount actually been paid or received? This changes your bank balance today.", parent=self.window):
            self.store.settle(int(identity),due); self.refresh()

    def pot(self):
        self.form("Savings goal", [('name','Goal','',None), ('target','Target amount (£)','',None), ('date','Target YYYY-MM-DD (optional)','',None)], lambda v:self.store.add_pot(v['name'],pence(v['target']),v['date'] or None))

    def move_pot(self):
        identity = int(self.selected(self.pots))
        self.form("Allocate or release savings", [('amount','£: positive allocates, negative releases','',None)],lambda v:self.store.move_pot(identity,pence(v['amount'])))

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self.window, title="PRIVATE financial backup — do not publish", defaultextension='.sqlite3', filetypes=[('Private SQLite database','*.sqlite3')])
        if path:
            self.store.backup(path)
            messagebox.showinfo("Private backup", "Saved. This file contains your financial records; keep it private.", parent=self.window)


def open_finance(parent=None):
    instance = FinanceWindow(parent)
    if parent is None:
        instance.window.mainloop()
    return instance
