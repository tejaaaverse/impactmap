"""Tests for validators."""

from utils.validators import validate_number, validate_positive
import pytest


def test_validate_number_valid():
    validate_number(42)
    validate_number(3.14)
    validate_number(0)
    validate_number(-1)


def test_validate_number_invalid_type():
    with pytest.raises(TypeError):
        validate_number("hello")
    with pytest.raises(TypeError):
        validate_number(None)
    with pytest.raises(TypeError):
        validate_number([1, 2])


def test_validate_number_nan():
    with pytest.raises(ValueError):
        validate_number(float("nan"))


def test_validate_positive():
    validate_positive(1)
    validate_positive(0.001)


def test_validate_positive_invalid():
    with pytest.raises(ValueError):
        validate_positive(0)
    with pytest.raises(ValueError):
        validate_positive(-5)
