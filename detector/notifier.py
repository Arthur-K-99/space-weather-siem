"""Pluggable notifier interface.

The triage flow is the alerts index + Kibana dashboards (M6), so the default
notifier just logs. The Notifier protocol is the seam where a webhook/Slack/email
sink could be added later without touching the engine.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("detector")


class Notifier(Protocol):
    def notify(self, kind: str, alert: dict) -> None:
        """kind is "new" (first time in a bucket) or "escalated" (severity rose)."""
        ...


class LogNotifier:
    def notify(self, kind: str, alert: dict) -> None:
        log.warning(
            "ALERT[%s] %s | sev=%d count=%d fp=%s",
            kind,
            alert["message"],
            alert["event"]["severity"],
            alert["alert"]["count"],
            alert["alert"]["fingerprint"][:12],
        )


class NullNotifier:
    def notify(self, kind: str, alert: dict) -> None:
        pass
