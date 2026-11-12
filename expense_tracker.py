"""A small CSV-backed command-line expense tracker."""

import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

CSV_HEADERS = ("date", "description", "category", "amount")


def load_expenses(path: Path) -> list[dict[str, str]]:
    """Load expenses from *path*, returning an empty list if it does not exist."""
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != list(CSV_HEADERS):
            raise ValueError(
                f"{path} must have these columns: {', '.join(CSV_HEADERS)}"
            )
        return list(reader)


def add_expense(
    path: Path, expense_date: str, description: str, category: str, amount: Decimal
) -> None:
    """Append one validated expense to the CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        if needs_header:
            writer.writeheader()
        writer.writerow(
            {
                "date": expense_date,
                "description": description,
                "category": category,
                "amount": f"{amount:.2f}",
            }
        )


def summarize_expenses(
    expenses: list[dict[str, str]],
) -> tuple[Decimal, dict[str, Decimal]]:
    """Return the total and category totals for loaded expenses."""
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    for expense in expenses:
        try:
            amount = Decimal(expense["amount"])
        except (KeyError, InvalidOperation) as exc:
            raise ValueError("CSV contains an invalid amount.") from exc
        by_category[expense["category"]] += amount
    return sum(by_category.values(), Decimal("0")), dict(sorted(by_category.items()))


def _prompt_nonempty(
    prompt: str, input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> str:
    while True:
        value = input_fn(prompt).strip()
        if value:
            return value
        output_fn("Please enter a value.")


def _prompt_date(
    input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> str:
    while True:
        value = input_fn(f"Date (YYYY-MM-DD, default {date.today()}): ").strip()
        if not value:
            return date.today().isoformat()
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            output_fn("Enter a valid date in YYYY-MM-DD format.")
        else:
            return parsed.isoformat()


def _prompt_amount(
    input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> Decimal:
    while True:
        value = input_fn("Amount: ").strip()
        try:
            amount = Decimal(value)
            amount = amount.quantize(Decimal("0.01"))
        except InvalidOperation:
            output_fn("Enter a valid positive amount, for example 12.50.")
            continue
        if not amount.is_finite() or amount <= 0:
            output_fn("Amount must be greater than zero.")
            continue
        return amount


def _add_expense_interactively(
    path: Path,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> None:
    expense_date = _prompt_date(input_fn, output_fn)
    description = _prompt_nonempty("Description: ", input_fn, output_fn)
    category = _prompt_nonempty("Category: ", input_fn, output_fn)
    amount = _prompt_amount(input_fn, output_fn)
    add_expense(path, expense_date, description, category, amount)
    output_fn("Expense added.")


def _list_expenses(
    expenses: list[dict[str, str]], output_fn: Callable[[str], None]
) -> None:
    if not expenses:
        output_fn("No expenses recorded.")
        return
    output_fn(f"{'Date':<12} {'Description':<24} {'Category':<16} Amount")
    output_fn("-" * 64)
    for expense in expenses:
        output_fn(
            f"{expense['date']:<12} {expense['description'][:24]:<24} "
            f"{expense['category'][:16]:<16} {Decimal(expense['amount']):>10.2f}"
        )


def _print_summary(
    expenses: list[dict[str, str]], output_fn: Callable[[str], None]
) -> None:
    total, by_category = summarize_expenses(expenses)
    if not by_category:
        output_fn("No expenses recorded.")
        return
    output_fn(f"Total: {total:.2f}")
    output_fn("By category:")
    for category, amount in by_category.items():
        output_fn(f"  {category}: {amount:.2f}")


def run(
    csv_path: str | Path = "expenses.csv",
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Run the interactive expense tracker menu."""
    path = Path(csv_path)
    while True:
        output_fn("\nExpense Tracker")
        output_fn("1. Add expense")
        output_fn("2. List expenses")
        output_fn("3. Summarize expenses")
        output_fn("4. Exit")
        choice = input_fn("Choose an option: ").strip()

        try:
            expenses = load_expenses(path)
            if choice == "1":
                _add_expense_interactively(path, input_fn, output_fn)
            elif choice == "2":
                _list_expenses(expenses, output_fn)
            elif choice == "3":
                _print_summary(expenses, output_fn)
            elif choice == "4":
                output_fn("Goodbye!")
                return
            else:
                output_fn("Please choose 1, 2, 3, or 4.")
        except (OSError, ValueError) as exc:
            output_fn(f"Error: {exc}")


def main() -> None:
    try:
        run(sys.argv[1] if len(sys.argv) > 1 else "expenses.csv")
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
