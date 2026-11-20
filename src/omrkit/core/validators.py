"""Built-in field and identity checksum validators (including Turkish TC Kimlik No)."""

from __future__ import annotations

from omrkit.models.template import ValidatorType


def validate_tr_tckn(value: str) -> bool:
    """Validate an 11-digit Turkish Republic Identity Number (TC Kimlik No)."""
    digits = value.strip()
    if len(digits) != 11 or not digits.isdigit() or digits[0] == "0":
        return False
    nums = [int(ch) for ch in digits]
    odd_sum = sum(nums[0:9:2])  # 1st, 3rd, 5th, 7th, 9th
    even_sum = sum(nums[1:8:2])  # 2nd, 4th, 6th, 8th
    d10 = ((odd_sum * 7) - even_sum) % 10
    d11 = sum(nums[0:10]) % 10
    return nums[9] == d10 and nums[10] == d11


def validate_luhn(value: str) -> bool:
    """Validate a numeric identifier using the standard Luhn mod-10 checksum."""
    digits = value.strip()
    if len(digits) < 2 or not digits.isdigit():
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def validate_digits(value: str) -> bool:
    """Verify the value consists solely of ASCII digits and is non-empty."""
    stripped = value.strip()
    return bool(stripped) and stripped.isdigit()


def validate_non_empty(value: str) -> bool:
    """Verify the value is non-empty."""
    return bool(value.strip())


def run_validator(validator_type: ValidatorType, value: str) -> tuple[bool, str]:
    """Run a named field validator and return (is_valid, reason_message)."""
    if validator_type == "tr_tckn":
        ok = validate_tr_tckn(value)
        return ok, "" if ok else f"Invalid Turkish TC Kimlik No checksum: '{value}'."
    if validator_type == "luhn":
        ok = validate_luhn(value)
        return ok, "" if ok else f"Invalid Luhn checksum: '{value}'."
    if validator_type == "digits":
        ok = validate_digits(value)
        return ok, "" if ok else f"Expected numeric digits only, got '{value}'."
    if validator_type == "non_empty":
        ok = validate_non_empty(value)
        return ok, "" if ok else "Required field was left blank."
    return True, ""
