import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.finance import FinanceStore, calculate_budget, occurrences, pence


class BudgetTests(unittest.TestCase):
    def test_spec_example_and_rounding(self):
        result = calculate_budget(300000, 115000, 50000, 35000, 20)
        self.assertEqual((result['spendable'], result['daily'], result['weekly']), (100000, 5000, 35000))
        self.assertEqual(calculate_budget(100,0,0,0,3)['daily'],33)

    def test_tomorrow_and_danger(self):
        self.assertEqual(calculate_budget(12000,0,0,0,1)['weekly'],12000)
        result = calculate_budget(10000,12000,1000,1000,5)
        self.assertEqual((result['risk'],result['shortfall'],result['daily']),('danger',4000,0))
        for days in (0,-1):
            with self.assertRaises(ValueError):
                calculate_budget(0,0,0,0,days)

    def test_money_is_exact_and_validated(self):
        self.assertEqual(pence('17.99'),1799)
        for value in ('NaN','Infinity','1.001','abc'):
            with self.assertRaises(ValueError):
                pence(value)
        with self.assertRaises(ValueError):
            calculate_budget(1.0,0,0,0,1)

    def test_month_end_and_leap_year_recurrence(self):
        self.assertEqual(list(occurrences(date(2026,1,31),'monthly',date(2026,3,31))),
                         [date(2026,1,31),date(2026,2,28),date(2026,3,31)])
        dates=list(occurrences(date(2024,2,29),'yearly',date(2028,3,1)))
        self.assertEqual(dates[1],date(2025,2,28))
        self.assertEqual(dates[-1],date(2028,2,29))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=FinanceStore(Path(self.temp.name)/'finance.sqlite3')
        self.today=date.today()
        self.store.reconcile(300000)
        self.store.configure((self.today+timedelta(days=20)).isoformat(),35000,20000)

    def tearDown(self):
        self.temp.cleanup()

    def schedule(self,kind='bill',amount=10000,offset=2,frequency='once'):
        due=(self.today+timedelta(days=offset)).isoformat()
        identity=self.store.add_schedule('Test',amount,kind,due,frequency,'General')
        return identity,due

    def test_expected_income_then_received_once(self):
        identity,due=self.schedule('income',100000)
        self.assertEqual(self.store.balance(),300000)
        self.assertEqual(self.store.forecast(3)[-1]['balance'],400000)
        self.store.settle(identity,due)
        self.assertEqual(self.store.balance(),400000)
        self.assertEqual(self.store.forecast(3)[-1]['balance'],400000)
        with self.assertRaises(ValueError):
            self.store.settle(identity,due)

    def test_paid_bill_preserves_spendable_and_delete_reopens(self):
        identity,due=self.schedule()
        before=self.store.summary()['spendable']
        self.store.settle(identity,due)
        self.assertEqual(self.store.balance(),290000)
        self.assertEqual(self.store.summary()['commitments'],0)
        self.assertEqual(self.store.summary()['spendable'],before)
        self.store.delete_transaction(self.store.transactions()[0]['id'])
        self.assertEqual(self.store.summary()['commitments'],10000)
        self.assertEqual(self.store.balance(),300000)

    def test_savings_traceability_and_underfunded_warning(self):
        pot=self.store.add_pot('Goal',500000)
        self.store.move_pot(pot,50000)
        self.assertEqual(self.store.balance(),300000)
        self.assertEqual(self.store.summary()['reserved'],50000)
        self.store.move_pot(pot,-10000)
        self.assertEqual(len(self.store.movements()),2)
        with self.assertRaises(ValueError):
            self.store.move_pot(pot,-50000)
        self.store.move_pot(pot,300000)
        self.assertEqual(self.store.summary()['risk'],'danger')
        self.assertTrue(any('exceed the cash' in n for n in self.store.summary()['notices']))

    def test_transaction_edit_delete_recalculate(self):
        before=self.store.summary()['daily']
        identity=self.store.transaction('Food',-2000,self.today.isoformat(),'Food')
        self.assertLess(self.store.summary()['daily'],before)
        self.store.transaction('Food',-1000,self.today.isoformat(),'Food',identity)
        self.assertEqual(self.store.balance(),299000)
        self.store.delete_transaction(identity)
        self.assertEqual(self.store.balance(),300000)

    def test_reconciliation_is_a_record_and_persists(self):
        self.store.reconcile(123456)
        reopened=FinanceStore(self.store.path)
        self.assertEqual(reopened.balance(),123456)
        self.assertEqual(len(reopened.transactions()),2)

    def test_invalid_inputs_and_missing_payday(self):
        with self.assertRaises(ValueError):
            self.schedule(amount=-10)
        with self.assertRaises(ValueError):
            self.store.transaction('Future',100,(self.today+timedelta(days=1)).isoformat(),'Test')
        self.store.configure(self.today.isoformat(),0,0)
        self.assertIsNone(self.store.summary()['daily'])
        with self.store.connect() as db:
            db.execute('UPDATE settings SET payday=NULL')
        self.assertIsNone(self.store.summary()['weekly'])

    def test_same_day_low_point_and_overdue_income(self):
        self.schedule('bill',400000)
        self.schedule('income',500000)
        row=self.store.forecast(2)[-1]
        self.assertEqual(row['balance'],400000)
        self.assertEqual(row['low'],-100000)
        self.assertGreater(row['shortfall'],0)
        self.schedule('income',50000,offset=-1)
        self.assertEqual(self.store.forecast(2)[-1]['balance'],400000)

    def test_overdue_bill_and_payday_bill_reserved(self):
        self.schedule(offset=-1)
        self.schedule(offset=20)
        self.assertEqual(self.store.summary()['commitments'],20000)
        self.assertEqual(self.store.forecast(1)[0]['balance'],290000)

    def test_stop_schedule_keeps_paid_transactions(self):
        identity,due=self.schedule(frequency='weekly')
        self.store.settle(identity,due)
        self.store.stop_schedule(identity)
        self.assertEqual(self.store.balance(),290000)
        self.assertEqual(self.store.summary()['commitments'],0)

    def test_linked_transaction_cannot_reverse_direction(self):
        identity,due=self.schedule()
        self.store.settle(identity,due)
        transaction=self.store.transactions()[0]
        with self.assertRaises(ValueError):
            self.store.transaction('Wrong',100,self.today.isoformat(),'Test',transaction['id'])

    def test_backup_restore(self):
        backup=Path(self.temp.name)/'backup.sqlite3'
        self.store.backup(backup)
        self.assertEqual(FinanceStore(backup).balance(),300000)


class FinanceUITests(unittest.TestCase):
    def test_window_renders_local_records(self):
        import tkinter as tk
        from app.finance_ui import FinanceWindow
        with tempfile.TemporaryDirectory() as temp:
            store=FinanceStore(Path(temp)/'test.sqlite3')
            try:
                ui=FinanceWindow(store=store)
            except tk.TclError as exc:
                self.skipTest(str(exc))
            try:
                ui.window.withdraw()
                ui.window.update_idletasks()
                self.assertEqual(len(ui.notebook.tabs()),5)
                self.assertIn('SETUP NEEDED',ui.totals.get())
                self.assertEqual(len(ui.forecast_table.get_children()),91)
            finally:
                ui.window.destroy()
