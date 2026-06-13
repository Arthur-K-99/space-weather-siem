"""Per-feed poll cadence.

Each feed declares a GROUP; the interval for a group comes from an env var (so
docker-compose / .env can tune it) with a sensible default. Read at runtime,
after .env is loaded.
"""

from __future__ import annotations

import os

# group -> (env var, default seconds)
_GROUPS = {
    "realtime": ("POLL_INTERVAL_REALTIME", 60),  # 1-min feeds: Kp, X-ray, solar wind
    "slow": ("POLL_INTERVAL_SLOW", 300),  # protons (5-min), NOAA scales, SWPC alerts
    "donki": ("POLL_INTERVAL_DONKI", 900),  # NASA DONKI event catalog
}


def interval_for(feed) -> int:
    """Resolve a feed's poll interval in seconds from its GROUP."""
    env_var, default = _GROUPS[feed.GROUP]
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default
