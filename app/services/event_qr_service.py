from __future__ import annotations

"""Compatibility shell for QR attendance links created before the code flow.

QR attendance is intentionally retired. The participant QR router is no longer
registered, and legacy signed links are rejected here so an old screenshot can
never confirm attendance or award points after the migration to per-event codes.
"""

CHECKIN_EVENT_STATUSES: set[str] = set()


def qr_png(_link: str) -> bytes:
    raise RuntimeError("QR attendance has been retired")


async def check_in(*_args, **_kwargs):
    raise ValueError("event_not_open")
