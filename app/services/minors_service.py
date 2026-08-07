"""Minors-detection technical scaffolding — not a policy or gating decision.

`birth_date`/`age` are collected at registration (see
app/repositories/users.py) but, before this module, were never used to
compute anything about age-appropriateness anywhere in the app — see
docs/PRODUCTION_READINESS_AUDIT.md finding #17. `is_minor()` is a pure,
read-only function: it answers "does the data on file suggest this
person is under 18", nothing more. It does not restrict, block, gate, or
change behavior for anyone — it is used exactly once, as an
admin-only informational label (see app/services/admin_user_card.py),
so the data is visible if/when the platform owner decides what to do
about it. Enabling any actual restriction based on this is explicitly a
legal/organizational decision for the owner (and likely counsel), not
something this function or its one call site should ever be extended to
do unilaterally.
"""

from __future__ import annotations

DEFAULT_ADULT_AGE = 18


def is_minor(age: int | None, *, adult_age: int = DEFAULT_ADULT_AGE) -> bool | None:
    """Returns None (unknown, not "not a minor") when age wasn't collected —
    callers must not treat unknown as either answer."""
    if age is None:
        return None
    return age < adult_age
