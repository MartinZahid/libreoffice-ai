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
    "INDIRECT",
)
_DANGEROUS_RE = re.compile(
    r"\b(" + "|".join(DANGEROUS_FUNCTIONS) + r")\s*\(",
    re.IGNORECASE,
)
_FORMULA_WITHOUT_EQUALS_RE = re.compile(r"^[+@]\s*[A-Za-z(]|^-\s*[A-Za-z(]")
_EXTERNAL_REFERENCE_RE = re.compile(r"#\s*[\$A-Za-z']|'\s*#")


def validate_formula(text: str) -> None:
    """Reject formulas that can contact external resources."""
    if not isinstance(text, str) or not text:
        return

    if not text.startswith("="):
        if _FORMULA_WITHOUT_EQUALS_RE.match(text):
            raise ValueError(
                "Las fórmulas deben empezar por =. Para guardar texto literal, "
                "evita iniciarlo con +, - o @."
            )
        return

    if _EXTERNAL_REFERENCE_RE.search(text):
        raise ValueError(
            "La fórmula contiene una referencia externa, que está bloqueada por seguridad."
        )

    match = _DANGEROUS_RE.search(text)
    if match:
        raise ValueError(
            f"La fórmula usa la función {match.group(1).upper()}, que puede acceder a "
            "recursos externos y está bloqueada por seguridad."
        )
