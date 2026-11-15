"""Normalize and validate the MVP's email and phone login identifiers."""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise ValidationError("Enter a valid email address.") from exc
    return normalized


def normalize_phone(value: str) -> str:
    """Return an E.164-style number; unprefixed 10-digit numbers are Indian."""
    raw = value.strip()
    compact = re.sub(r"[\s().-]", "", raw)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact.startswith("+"):
        digits = compact[1:]
        if not digits.isdigit() or not 8 <= len(digits) <= 15 or digits.startswith("0"):
            raise ValidationError("Enter a valid international phone number.")
        return "+" + digits

    if not compact.isdigit():
        raise ValidationError("Enter a valid phone number.")
    if len(compact) == 10:
        return "+91" + compact
    if len(compact) == 11 and compact.startswith("0"):
        return "+91" + compact[1:]
    if len(compact) == 12 and compact.startswith("91"):
        return "+" + compact
    raise ValidationError("Enter a 10-digit Indian number or a number with its country code.")
