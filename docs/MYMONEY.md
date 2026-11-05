# MyMoney inside Oracle

MyMoney is a local web workspace in Oracle. It works without an API key, Google
connection or internet access. Launch `python oracle.py --money` or choose
**MyMoney** in the web sidebar. It uses the same `.data/finance.sqlite3` database
as the previous desktop version. The legacy desktop remains under `--desktop`.

## First use

1. Set your actual bank balance. This creates an explicit reconciliation transaction.
2. Set the next payday, safety buffer and caution threshold.
3. Add bills and income schedules. Start on the first **unpaid** occurrence, not
   the original subscription start date. Choose once, weekly, monthly or yearly.
4. Create savings pots and allocate funds. Allocations reserve existing cash;
   they do not reduce your bank balance.
5. Record purchases as negative transactions and income as positive transactions.
   For a planned bill or salary, select its occurrence on Overview and choose
   **Record payment / receipt**, instead of adding a separate transaction.

Only record money actually received or paid. Recording a scheduled occurrence
early is supported, but it changes cash today. Repeated recording is rejected.
For a variable bill, mark the estimate paid, then edit the linked transaction
to the amount actually paid. For later occurrences, stop the old schedule and
add its replacement. Stopping a schedule removes all its unpaid occurrences.

## Budget rules

All persisted amounts and budget calculations use integer pence. Text input uses
Decimal; more than two decimal places, nonfinite values and negative bill amounts
are rejected. The initial release supports one GBP account.

Spendable = max(0, actual cash − unpaid bills − reserved pots − safety buffer).
Daily allowance is spendable divided by days until payday, rounded down to pence.
Weekly allowance is daily allowance times min(7, days remaining).

Unpaid commitments include overdue bills and bills on payday, conservatively
assuming bills may leave before salary arrives. Expected salary is not spendable
cash. Missing, current or overdue payday pauses allowances rather than dividing
by zero. The preview then covers 30 days until a future payday is configured.

Danger means commitments plus protected reserves exceed cash. Caution means the
remaining spendable amount is at or below the configured warning threshold.
Warnings explain shortfalls, underfunded pots, overdue entries and bills due
within seven days. These are shown in the app, not OS push notifications.

## Forecast assumptions

The 90-day daily forecast includes unpaid scheduled income on its due date and
bills on their due dates. Overdue bills are due immediately; overdue income is
not assumed to arrive. Bills precede income on the same date, so the table shows
both the low balance before income and the closing balance. Shortfalls compare
the low balance with the safety buffer plus all reserved pots.

Paid/received occurrences are excluded because their transactions are already in
cash. Monthly dates preserve their anchor (31 January → 28 February → 31 March).
Annual leap-day schedules return to 29 February in leap years. Estimated entries
are explicitly marked, but treated as their entered amounts in calculations.
The chart is scheduled cashflow only: it does not assume future discretionary
spending, bank holidays, interest, taxes, exchange rates or bank processing times.

## Storage and privacy

The private SQLite database is `.data/finance.sqlite3`, covered by `.gitignore`.
Tables separate settings, transactions, schedules, pots and allocation movements.
Transactions optionally reference a unique schedule/date occurrence; removing a
linked payment reopens that occurrence. Database writes use SQLite transactions
and foreign keys. Schema version 1 is recorded with `PRAGMA user_version`.

No finance data is supplied to LLM tools, sent to Gmail, or included in public
source releases. As with any window, explicitly sharing a screenshot or pasting
its contents into chat can disclose data. The database is not encrypted: protect
your Windows account and disk. Never store bank passwords or card details.

The legacy desktop's **Private database backup** creates a consistent SQLite copy. That copy contains
personal records and is separate from the sanitized source-only E: backup.
To restore: close Oracle, retain a copy of the current database, and copy the
private backup to `.data/finance.sqlite3`. Reopen MyMoney and verify its balance.
Automated tests verify backup round-trip, not a destructive restore over real data.

## Validation and remaining work

Run `python -m unittest discover -s tests -v`. Tests cover the specification's
budget example, penny rounding, paid/expected income, duplicate payments, paid
bills, savings allocations/releases, shortfalls, tomorrow's payday, transaction
edits/deletions, negative bills, annual/monthly dates, missing payday, reconciliation,
overdue entries, same-day cash shortages, persistence and private backup recovery.
A desktop smoke test checks all five tabs using a temporary database.

Backlog: bank synchronization through an authorized Open Banking provider,
multi-account/currency support, bank-holiday payday rules, OS notifications,
spending-rate forecasts, transaction-to-bill matching, encrypted storage,
versioned schema migrations and in-app backup restore. The web dashboard uses
local-only `/api/money` read/action endpoints; no hosted service is introduced.
