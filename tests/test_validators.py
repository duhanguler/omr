"""Unit tests for Turkish TC Kimlik No, Luhn, and generic field validators."""

from __future__ import annotations

from omrkit.core.validators import (
    run_validator,
    validate_digits,
    validate_luhn,
    validate_non_empty,
    validate_tr_tckn,
)


def test_turkish_tckn_checksum() -> None:
    # Mathematically valid synthetic TC Kimlik No: 10000000146
    assert validate_tr_tckn("10000000146") is True
    # Invalid checksum, wrong length, leading zero, non-digits
    assert validate_tr_tckn("10000000147") is False
    assert validate_tr_tckn("00000000146") is False
    assert validate_tr_tckn("12345") is False
    assert validate_tr_tckn("1000000014A") is False


def test_luhn_and_generic_validators() -> None:
    assert validate_luhn("79927398713") is True
    assert validate_luhn("79927398714") is False
    assert validate_digits("190735") is True
    assert validate_digits("") is False
    assert validate_non_empty("A") is True
    assert validate_non_empty("   ") is False

    ok, msg = run_validator("tr_tckn", "12345678901")
    assert ok is False
    assert "TC Kimlik" in msg
