"""One module per source feed. Each exposes FEED, URL, fetch(session), normalize(records)."""

from collector.feeds import kp_index, xray

# Feeds the poller iterates over. M3 extends this list.
ALL = (kp_index, xray)

__all__ = ["ALL", "kp_index", "xray"]
