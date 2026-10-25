from __future__ import annotations

import logging
import unittest

from app.request_context import RequestIDLogFilter, new_request_id, request_id_var


class NewRequestIdTests(unittest.TestCase):
    def test_generates_a_fresh_id_when_no_incoming_header(self) -> None:
        first = new_request_id(None)
        second = new_request_id(None)
        self.assertTrue(first)
        self.assertNotEqual(first, second)

    def test_trusts_an_incoming_request_id_as_is(self) -> None:
        self.assertEqual(new_request_id("upstream-abc-123"), "upstream-abc-123")

    def test_empty_string_header_is_treated_as_absent(self) -> None:
        # An empty X-Request-ID header (technically present, semantically
        # nothing) should still generate a real ID rather than propagate ""
        # into every log line for the request.
        generated = new_request_id("")
        self.assertNotEqual(generated, "")


class RequestIDLogFilterTests(unittest.TestCase):
    def _record(self) -> logging.LogRecord:
        return logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello", args=(), exc_info=None,
        )

    def test_attaches_the_current_context_id_to_the_record(self) -> None:
        token = request_id_var.set("req-42")
        try:
            record = self._record()
            self.assertTrue(RequestIDLogFilter().filter(record))
            self.assertEqual(record.request_id, "req-42")
        finally:
            request_id_var.reset(token)

    def test_defaults_to_a_placeholder_outside_a_request(self) -> None:
        # No token set — this simulates a log line from startup or a
        # background task not tied to any HTTP request.
        record = self._record()
        RequestIDLogFilter().filter(record)
        self.assertEqual(record.request_id, "-")


if __name__ == "__main__":
    unittest.main()
