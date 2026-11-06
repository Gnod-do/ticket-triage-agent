"""Regex-based PII masking applied before any text reaches a model or a report.

Production would add NER for person names; regexes cover the structured identifiers
that appear in support tickets (phones, e-mails, INN, card numbers).
"""
import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)")
_PHONE = re.compile(r"(?<![\w\d])(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
_INN = re.compile(r"(?<!\d)(?:\d{12}|\d{10})(?!\d)")


def mask_pii(text: str) -> str:
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CARD.sub("[CARD]", text)
    text = _PHONE.sub("[PHONE]", text)
    text = _INN.sub("[INN]", text)
    return text
