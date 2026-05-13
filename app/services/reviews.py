"""Reviewer-side rule helpers shared by detail payload + decision/override APIs.

`compute_effective_verdict` centralizes the rule: an override row, if present,
wins; otherwise the model verdict from the comparison row stands. See
data-model.md § Effective verdict.
"""

from __future__ import annotations

from app.db.models import Comparison, FieldOverride


def compute_effective_verdict(
    comparison: Comparison,
    override: FieldOverride | None,
) -> str:
    """Return the effective verdict the UI should render for a field.

    Override values are limited to `pass`/`fail`; comparison verdicts include
    `not_applicable`. The override always wins when present — by design, a
    reviewer can flip a `pass` to `fail` or vice-versa, but the
    `not_applicable` state is never overridable (the field doesn't apply to
    this submission). Callers that need to enforce "override forbidden on
    not_applicable" should do so at the API boundary; this helper just
    encodes the read-time rule.
    """
    if override is not None:
        return override.override_verdict
    return comparison.verdict
