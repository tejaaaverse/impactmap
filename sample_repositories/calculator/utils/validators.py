"""Input validation utilities."""


def validate_number(value) -> None:
    """Validate that the input is a number."""
    if not isinstance(value, (int, float)):
        raise TypeError(f"Expected a number, got {type(value).__name__}")
    if isinstance(value, float) and (value != value):  # NaN check
        raise ValueError("NaN is not a valid number")


def validate_positive(value: float) -> None:
    """Validate that a number is positive."""
    validate_number(value)
    if value <= 0:
        raise ValueError(f"Expected positive number, got {value}")
