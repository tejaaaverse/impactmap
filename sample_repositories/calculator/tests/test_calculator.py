"""Tests for the Calculator class."""

from calculator import Calculator
import pytest


class TestCalculator:
    def setup_method(self):
        self.calc = Calculator()

    def test_add(self):
        assert self.calc.calculate("add", 2, 3) == 5

    def test_subtract(self):
        assert self.calc.calculate("subtract", 10, 4) == 6

    def test_multiply(self):
        assert self.calc.calculate("multiply", 3, 4) == 12

    def test_divide(self):
        assert self.calc.calculate("divide", 10, 2) == 5

    def test_divide_by_zero(self):
        with pytest.raises(ValueError):
            self.calc.calculate("divide", 10, 0)

    def test_unknown_operation(self):
        with pytest.raises(ValueError):
            self.calc.calculate("modulo", 10, 3)

    def test_history(self):
        self.calc.calculate("add", 1, 2)
        self.calc.calculate("multiply", 3, 4)
        assert len(self.calc.get_history()) == 2

    def test_clear_history(self):
        self.calc.calculate("add", 1, 2)
        self.calc.clear_history()
        assert len(self.calc.get_history()) == 0

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            self.calc.calculate("add", "not", "numbers")
