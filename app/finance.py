"""Local, single-account GBP budgeting. All stored amounts are integer pence.

This module has no network or LLM dependency. Expected income is never cash.
"""
from __future__ import annotations

import calendar
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


def pence(value: str) -> int:
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Use a finite amount with at most two decimal places.")
        if abs(amount) > Decimal("1000000000"):
            raise ValueError("Amount is too large.")
        return int(amount * 100)
    except InvalidOperation as exc:
        raise ValueError("Enter an amount such as 125.50.") from exc


def money(amount: int) -> str:
    return f"£{Decimal(amount) / 100:,.2f}"


def integer(value, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError("Invalid amount in pence.")
    if abs(value) > 100_000_000_000:
        raise ValueError("Amount is too large.")
    return value


def text(value):
    value = str(value).strip()
    if not value or len(value) > 120:
        raise ValueError("Enter a name or category of 1–120 characters.")
    return value


def calculate_budget(current_balance, upcoming_bills, reserved_savings, safety_buffer,
                     days_until_payday, warning_threshold=20000):
    """Inputs and outputs use pence; allowances round down, never overspend."""
    integer(current_balance)
    for amount in (upcoming_bills, reserved_savings, safety_buffer, warning_threshold):
        integer(amount, 0)
    if type(days_until_payday) is not int or days_until_payday <= 0:
        raise ValueError("Set a future payday before calculating allowances.")
    remainder = current_balance - upcoming_bills - reserved_savings - safety_buffer
    spendable = max(0, remainder)
    daily = spendable // days_until_payday
    return dict(spendable=spendable, daily=daily,
                weekly=daily * min(7, days_until_payday), shortfall=max(0, -remainder),
                risk="danger" if remainder < 0 else "caution" if remainder <= warning_threshold else "safe")


def occurrences(start: date, frequency: str, end: date):
    """Preserve the original day across short months (Jan 31 → Feb 28 → Mar 31)."""
    if frequency not in ("once", "weekly", "monthly", "yearly"):
        raise ValueError("Choose once, weekly, monthly or yearly.")
    current, index = start, 0
    while current <= end:
        yield current
        index += 1
        if frequency == "once":
            break
        if frequency == "weekly":
            current = start + timedelta(weeks=index)
        else:
            month = start.month - 1 + index * (12 if frequency == "yearly" else 1)
            year, month = start.year + month // 12, month % 12 + 1
            current = date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


class FinanceStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parent.parent / ".data" / "finance.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK(id=1), opening INTEGER NOT NULL DEFAULT 0,
                    payday TEXT, buffer INTEGER NOT NULL DEFAULT 0 CHECK(buffer>=0),
                    warning INTEGER NOT NULL DEFAULT 20000 CHECK(warning>=0));
                INSERT OR IGNORE INTO settings(id) VALUES(1);
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
                    kind TEXT NOT NULL CHECK(kind IN ('bill','income')), start TEXT NOT NULL,
                    frequency TEXT NOT NULL CHECK(frequency IN ('once','weekly','monthly','yearly')),
                    category TEXT NOT NULL, estimated INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, amount INTEGER NOT NULL,
                    day TEXT NOT NULL, category TEXT NOT NULL,
                    schedule_id INTEGER REFERENCES schedules(id), due TEXT,
                    UNIQUE(schedule_id,due));
                CREATE TABLE IF NOT EXISTS pots (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, target INTEGER NOT NULL CHECK(target>0),
                    target_date TEXT);
                CREATE TABLE IF NOT EXISTS movements (
                    id INTEGER PRIMARY KEY, pot_id INTEGER NOT NULL REFERENCES pots(id),
                    amount INTEGER NOT NULL, day TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connect() as db:
            return dict(db.execute("SELECT * FROM settings WHERE id=1").fetchone())

    def configure(self, payday, buffer, warning):
        payday = date.fromisoformat(payday).isoformat()
        integer(buffer, 0); integer(warning, 0)
        with self.connect() as db:
            db.execute("UPDATE settings SET payday=?,buffer=?,warning=? WHERE id=1", (payday, buffer, warning))

    def balance(self, today=None):
        today = today or date.today()
        with self.connect() as db:
            return db.execute("SELECT opening + (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE day<=?) FROM settings WHERE id=1", (today.isoformat(),)).fetchone()[0]

    def transactions(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM transactions ORDER BY day DESC,id DESC")]

    def transaction(self, name, amount, day, category, transaction_id=None):
        integer(amount)
        if not amount:
            raise ValueError("Transaction amount must not be zero.")
        day = date.fromisoformat(day).isoformat()
        if day > date.today().isoformat():
            raise ValueError("Record received/paid money only; use a schedule for future money.")
        with self.connect() as db:
            if transaction_id is None:
                return db.execute("INSERT INTO transactions(name,amount,day,category) VALUES(?,?,?,?)", (text(name), amount, day, text(category))).lastrowid
            row = db.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
            if not row:
                raise ValueError("Transaction no longer exists.")
            if row['schedule_id']:
                kind = db.execute("SELECT kind FROM schedules WHERE id=?", (row['schedule_id'],)).fetchone()[0]
                if (kind == 'bill' and amount >= 0) or (kind == 'income' and amount <= 0):
                    raise ValueError("Keep the payment direction of a linked transaction.")
            db.execute("UPDATE transactions SET name=?,amount=?,day=?,category=? WHERE id=?", (text(name), amount, day, text(category), transaction_id))

    def delete_transaction(self, transaction_id):
        with self.connect() as db:
            db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))

    def reconcile(self, actual, today=None):
        integer(actual)
        today = today or date.today()
        difference = actual - self.balance(today)
        if difference:
            self.transaction("Balance reconciliation", difference, today.isoformat(), "Adjustment")

    def add_schedule(self, name, amount, kind, start, frequency, category, estimated=False):
        integer(amount, 1)
        start_date = date.fromisoformat(start)
        start = start_date.isoformat()
        if start_date < date(2000, 1, 1) or start_date > date(2100, 1, 1):
            raise ValueError("Choose a schedule date between 2000 and 2100.")
        list(occurrences(start_date, frequency, start_date))
        if kind not in ("bill", "income"):
            raise ValueError("Choose bill or income.")
        with self.connect() as db:
            return db.execute("INSERT INTO schedules(name,amount,kind,start,frequency,category,estimated) VALUES(?,?,?,?,?,?,?)", (text(name), amount, kind, start, frequency, text(category), int(estimated))).lastrowid

    def schedules(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM schedules WHERE active=1 ORDER BY start,id")]

    def stop_schedule(self, schedule_id):
        with self.connect() as db:
            db.execute("UPDATE schedules SET active=0 WHERE id=?", (schedule_id,))

    def pending(self, end: date):
        with self.connect() as db:
            paid = {(r[0], r[1]) for r in db.execute("SELECT schedule_id,due FROM transactions WHERE schedule_id IS NOT NULL")}
        result = []
        for schedule in self.schedules():
            for due in occurrences(date.fromisoformat(schedule['start']), schedule['frequency'], end):
                if (schedule['id'], due.isoformat()) not in paid:
                    result.append(dict(schedule, due=due.isoformat()))
        return sorted(result, key=lambda r: (r['due'], r['id']))

    def settle(self, schedule_id, due, today=None):
        today = today or date.today()
        due_date = date.fromisoformat(due)
        with self.connect() as db:
            row = db.execute("SELECT * FROM schedules WHERE id=? AND active=1", (schedule_id,)).fetchone()
            if not row or due_date not in occurrences(date.fromisoformat(row['start']), row['frequency'], due_date):
                raise ValueError("This scheduled occurrence does not exist.")
            try:
                db.execute("INSERT INTO transactions(name,amount,day,category,schedule_id,due) VALUES(?,?,?,?,?,?)", (row['name'], row['amount'] * (-1 if row['kind'] == 'bill' else 1), today.isoformat(), row['category'], schedule_id, due))
            except sqlite3.IntegrityError as exc:
                raise ValueError("This occurrence is already recorded.") from exc

    def add_pot(self, name, target, target_date=None):
        integer(target, 1)
        if target_date:
            target_date = date.fromisoformat(target_date).isoformat()
        with self.connect() as db:
            return db.execute("INSERT INTO pots(name,target,target_date) VALUES(?,?,?)", (text(name), target, target_date or None)).lastrowid

    def pots(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT p.*,COALESCE(SUM(m.amount),0) AS reserved FROM pots p LEFT JOIN movements m ON p.id=m.pot_id GROUP BY p.id")]

    def move_pot(self, pot_id, amount):
        integer(amount)
        if not amount:
            raise ValueError("Enter a non-zero allocation or release.")
        with self.connect() as db:
            if not db.execute("SELECT id FROM pots WHERE id=?", (pot_id,)).fetchone():
                raise ValueError("Savings pot no longer exists.")
            reserved = db.execute("SELECT COALESCE(SUM(amount),0) FROM movements WHERE pot_id=?", (pot_id,)).fetchone()[0]
            if reserved + amount < 0:
                raise ValueError("Cannot release more than the pot contains.")
            db.execute("INSERT INTO movements(pot_id,amount,day) VALUES(?,?,?)", (pot_id, amount, date.today().isoformat()))

    def movements(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT m.*,p.name FROM movements m JOIN pots p ON p.id=m.pot_id ORDER BY m.id DESC")]

    def summary(self, today=None):
        today = today or date.today()
        settings = self.settings()
        payday = date.fromisoformat(settings['payday']) if settings['payday'] else None
        days = (payday - today).days if payday else 0
        end = payday if days > 0 else today + timedelta(days=30)
        # Include payday bills conservatively: bank processing order is unknown.
        pending = self.pending(end)
        commitments = sum(r['amount'] for r in pending if r['kind'] == 'bill')
        balance = self.balance(today)
        reserved = sum(p['reserved'] for p in self.pots())
        budget = calculate_budget(balance, commitments, reserved, settings['buffer'], max(1, days), settings['warning'])
        notices = []
        if days <= 0:
            notices.append("Set a future payday. Allowances are paused; preview covers the next 30 days.")
            budget.update(daily=None, weekly=None)
        if budget['shortfall']:
            notices.append(f"Commitments and protected reserves exceed cash by {money(budget['shortfall'])}.")
        elif budget['risk'] == 'caution':
            notices.append("Discretionary funds are at or below your warning threshold.")
        if reserved > balance:
            notices.append("Savings pots exceed the cash supporting them.")
        for row in pending:
            due = date.fromisoformat(row['due'])
            if due < today:
                notices.append(f"Overdue {'bill' if row['kind']=='bill' else 'expected income'}: {row['name']} ({row['due']}). Record it when actually paid/received.")
            elif row['kind'] == 'bill' and due <= today + timedelta(days=7):
                notices.append(f"Due {row['due']}: {row['name']} — {money(row['amount'])}.")
        return dict(budget, balance=balance, commitments=commitments, reserved=reserved,
                    buffer=settings['buffer'], days=days, pending=pending, notices=notices,
                    configured=days > 0, end=end)

    def forecast(self, days=90, today=None):
        if type(days) is not int or not 1 <= days <= 366:
            raise ValueError("Forecast range must be 1–366 days.")
        today = today or date.today()
        pending = self.pending(today + timedelta(days=days))
        current = self.balance(today)
        protected = self.settings()['buffer'] + sum(p['reserved'] for p in self.pots())
        rows = []
        for offset in range(days + 1):
            day = today + timedelta(days=offset)
            events = [r for r in pending if r['due'] == day.isoformat() or (offset == 0 and r['due'] < today.isoformat() and r['kind'] == 'bill')]
            # Bills first: show the low point before same-day income arrives.
            outflow = sum(r['amount'] for r in events if r['kind'] == 'bill')
            low = current - outflow
            current = low + sum(r['amount'] for r in events if r['kind'] == 'income')
            rows.append(dict(day=day.isoformat(), balance=current, low=low, protected=protected,
                             shortfall=max(0, protected-low)))
        return rows

    def backup(self, destination):
        """Explicit private backup, never part of a source release."""
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError("Choose a different backup path.")
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
