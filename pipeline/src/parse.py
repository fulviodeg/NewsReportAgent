"""Parse and normalize newsletter emails into discrete news items. Deterministic.

Splits each email into items (title, text, source link), stored with a foreign key to
the source email. A narrow LLM fallback for very messy emails is allowed but stays behind
a flag and does not run by default. See docs/v1-architecture.md (Section 4.2).
"""


def parse_email(raw_message) -> list:
    """Split one raw newsletter message into news items."""
    raise NotImplementedError
