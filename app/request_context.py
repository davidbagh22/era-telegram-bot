"""Per-request correlation ID — so a single production incident's log lines
can be grepped together, instead of interleaved with every other request
the process is handling at the same time.

Kept deliberately minimal: no external tracing service, no header beyond
`X-Request-ID` — a contextvar plus a logging filter is enough for
"which log lines belong to the same request," which is what production
readiness checklist item #213 actually asks for.
"""

from __future__ import annotations

import contextvars
import logging
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIDLogFilter(logging.Filter):
    """Attaches the current request's correlation ID to every log record
    emitted while handling it, so `%(request_id)s` can be used in the log
    format string (see `app/webapp.py::lifespan`'s `logging.basicConfig`).
    Records emitted outside of a request (startup, background tasks not
    tied to a request, the bot's own long-running dispatcher loop) get the
    default "-" rather than a stale or wrong ID.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def new_request_id(incoming: str | None) -> str:
    """A client-supplied `X-Request-ID` is trusted as-is if present (lets a
    request be traced across a future reverse proxy/load balancer that
    already assigns one) — otherwise a fresh one is generated. Either way
    it's just a correlation label, never used for authorization or trust
    decisions."""
    return incoming or uuid.uuid4().hex
