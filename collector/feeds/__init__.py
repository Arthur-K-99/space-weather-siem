"""One module per source feed. Each exposes FEED, GROUP, URL, fetch(session), normalize(records)."""

from collector.feeds import (
    donki_cme,
    donki_flr,
    donki_gst,
    donki_sep,
    kp_index,
    mag,
    noaa_scales,
    plasma,
    protons,
    swpc_alerts,
    xray,
)

# Feeds the poller iterates over.
ALL = (
    kp_index,
    xray,
    plasma,
    mag,
    protons,
    noaa_scales,
    swpc_alerts,
    donki_flr,
    donki_cme,
    donki_gst,
    donki_sep,
)

__all__ = [
    "ALL",
    "donki_cme",
    "donki_flr",
    "donki_gst",
    "donki_sep",
    "kp_index",
    "mag",
    "noaa_scales",
    "plasma",
    "protons",
    "swpc_alerts",
    "xray",
]
