"""Formula safety checks shared by Calc actions and tests."""

from __future__ import annotations

import re

DANGEROUS_FUNCTIONS = (
    "WEBSERVICE",
    "HYPERLINK",
    "DDE",
    "IMPORTXML",
    "IMPORTHTML",
    "IMPORTDATA",
    "IMPORTFEED",
    "RTD",
)
_DANGEROUS_RE = re.compile(
    r"\b(" + "|".join(DANGEROUS_FUNCTIONS) + r")\s*\(",
    re.IGNORECASE,
)


def validate_formula(text: str) -> None:
    """Reject formulas that can contact external resources."""
    if not isinstance(text, str) or not text.startswith("="):
        return
    match = _DANGEROUS_RE.search(text)
    if match:
        raise ValueError(
            f"La fórmula usa la función {match.group(1).upper()}, que puede acceder a "
            "recursos externos y está bloqueada por seguridad."
        )
