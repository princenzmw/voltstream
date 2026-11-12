import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from expense_tracker import add_expense, load_expenses, run, summarize_expenses


class ExpenseTrackerTests(unittest.TestCase):
    def test_add_and_load_expense(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expenses.csv"
            add_expense(path, "2026-11-12", "Lunch", "Food", Decimal("12.5"))

            self.assertEqual(
                load_expenses(path),
                [
                    {
                        "date": "2026-11-12",
                        "description": "Lunch",
                        "category": "Food",
                        "amount": "12.50",
                    }
                ],
            )

    def test_summary_groups_categories(self) -> None:
        expenses = [
            {"date": "2026-11-12", "description": "A", "category": "Food", "amount": "2.50"},
            {"date": "2026-11-12", "description": "B", "category": "Travel", "amount": "10.00"},
            {"date": "2026-11-12", "description": "C", "category": "Food", "amount": "1.25"},
        ]

        self.assertEqual(
            summarize_expenses(expenses),
            (Decimal("13.75"), {"Food": Decimal("3.75"), "Travel": Decimal("10.00")}),
        )

    def test_menu_adds_expense_and_summarizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expenses.csv"
            answers = iter(["1", "2026-11-12", "Coffee", "Food", "3.25", "3", "4"])
            output: list[str] = []

            run(path, lambda _: next(answers), output.append)

            self.assertIn("Expense added.", output)
            self.assertIn("Total: 3.25", output)

    def test_new_file_has_csv_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expenses.csv"
            add_expense(path, "2026-11-12", "Bus", "Travel", Decimal("2"))

            with path.open(newline="", encoding="utf-8") as file:
                self.assertEqual(next(csv.reader(file)), ["date", "description", "category", "amount"])


if __name__ == "__main__":
    unittest.main()
