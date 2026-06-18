from app.core.passwords import validate_password


def test_too_short_reports_length():
    msg = validate_password("ab1")
    assert msg and "8" in msg


def test_missing_digit_rejected():
    msg = validate_password("abcdefgh")
    assert msg and "number" in msg.lower()


def test_missing_letter_rejected():
    msg = validate_password("12345678")
    assert msg and "letter" in msg.lower()


def test_valid_password_passes():
    assert validate_password("abcdef12") is None


def test_empty_or_none_rejected():
    assert validate_password("") is not None
    assert validate_password(None) is not None
