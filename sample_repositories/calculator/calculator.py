"""
Sample Calculator Application.

A small Python project with known dependencies for testing
IMPACTMAP's analysis capabilities.
"""

from utils.math_helpers import add, subtract, multiply, divide
from utils.validators import validate_number


class Calculator:
    """A simple calculator with history tracking."""

    def __init__(self):
        self.history: list[str] = []

    def calculate(self, operation: str, a: float, b: float) -> float:
        """Perform a calculation and record it in history."""
        validate_number(a)
        validate_number(b)

        operations = {
            "add": add,
            "subtract": subtract,
            "multiply": multiply,
            "divide": divide,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation](a, b)
        self.history.append(f"{operation}({a}, {b}) = {result}")
        return result

    def get_history(self) -> list[str]:
        """Return calculation history."""
        return list(self.history)

    def clear_history(self) -> None:
        """Clear calculation history."""
        self.history.clear()
