#!/usr/bin/env python3
"""Generate the Kibana saved objects for the space-weather SIEM dashboards.

Dashboards-as-code: rather than hand-edit the dense, escaped NDJSON that Kibana
imports, we assemble the saved objects here as plain Python dicts and serialize
them to ``kibana/dashboards.ndjson``. That file is the committed deliverable;
``scripts/bootstrap.py`` imports it into Kibana via the saved-objects API.

Objects produced (classic aggregation-based visualizations — the most stable,
self-contained saved-object format, wired to data views via ``indexRefName``):

  - 2 data views (index-pattern):  space-weather-events, space-weather-alerts
  - visualizations grouped onto 4 dashboards:
      SOC Overview · Geomagnetic · Solar Activity · Pipeline Health

Run:  python scripts/build_dashboards.py   (writes kibana/dashboards.ndjson)
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "kibana" / "dashboards.ndjson"

KIBANA_VERSION = "9.4.2"

EVENTS_DV = "sws-events"
ALERTS_DV = "sws-alerts"

INDEX_REF = "kibanaSavedObjectMeta.searchSourceJSON.index"


# --- saved-object builders -------------------------------------------------


def data_view(
    obj_id: str,
    title: str,
    field_formats: dict | None = None,
    runtime_fields: dict | None = None,
) -> dict:
    attrs = {"title": title, "timeFieldName": "@timestamp", "name": title}
    if field_formats:
        # Per-field display formats (tooltips + axis labels).
        attrs["fieldFormatMap"] = json.dumps(field_formats)
    if runtime_fields:
        attrs["runtimeFieldMap"] = json.dumps(runtime_fields)
    return {
        "id": obj_id,
        "type": "index-pattern",
        "attributes": attrs,
        "references": [],
        "coreMigrationVersion": KIBANA_VERSION,
    }


def _search_source(kql: str) -> str:
    return json.dumps(
        {
            "query": {"query": kql, "language": "kuery"},
            "filter": [],
            "indexRefName": INDEX_REF,
        }
    )


def viz(obj_id: str, title: str, vis_state: dict, data_view_id: str, kql: str = "") -> dict:
    return {
        "id": obj_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "description": vis_state.pop("_description", ""),
            "uiStateJSON": "{}",
            "version": 1,
            "visState": json.dumps(vis_state),
            "kibanaSavedObjectMeta": {"searchSourceJSON": _search_source(kql)},
        },
        "references": [{"name": INDEX_REF, "type": "index-pattern", "id": data_view_id}],
        "coreMigrationVersion": KIBANA_VERSION,
    }


def _metric_agg(agg_id: str, agg_type: str, field: str | None, label: str) -> dict:
    params = {"field": field} if field else {}
    return {
        "id": agg_id,
        "enabled": True,
        "type": agg_type,
        "schema": "metric",
        "params": {**params, "customLabel": label},
    }


def metric_vis(metrics: list[tuple[str, str | None, str]], font_size: int = 36) -> dict:
    """A "big number" panel. ``metrics`` = [(agg_type, field, label), ...]."""
    aggs = [
        _metric_agg(str(i + 1), agg_type, field, label)
        for i, (agg_type, field, label) in enumerate(metrics)
    ]
    return {
        "title": "",
        "type": "metric",
        "aggs": aggs,
        "params": {
            "addTooltip": True,
            "addLegend": False,
            "type": "metric",
            "metric": {
                "percentageMode": False,
                "useRanges": False,
                "colorSchema": "Green to Red",
                "metricColorMode": "None",
                "colorsRange": [{"from": 0, "to": 10000}],
                "labels": {"show": True},
                "invertColors": False,
                "style": {
                    "bgFill": "#000",
                    "bgColor": False,
                    "labelColor": False,
                    "subText": "",
                    "fontSize": font_size,
                },
            },
        },
    }


def _category_axis() -> dict:
    return {
        "id": "CategoryAxis-1",
        "type": "category",
        "position": "bottom",
        "show": True,
        "style": {},
        "scale": {"type": "linear"},
        "labels": {"show": True, "filter": True, "truncate": 100},
        "title": {},
    }


def _value_axis(
    axis_id: str, position: str, title: str, scale: str, y_min: float | None = None
) -> dict:
    axis_scale: dict = {"type": scale, "mode": "normal"}
    if y_min is not None:
        # Pin the floor so a quiet baseline stays visible under a tall storm spike
        # (esp. on log axes, where auto-scaling clips low values).
        axis_scale.update({"defaultYExtents": False, "setYExtents": True, "min": y_min})
    return {
        "id": axis_id,
        "name": f"{position.capitalize()}Axis-{axis_id[-1]}",
        "type": "value",
        "position": position,
        "show": True,
        "style": {},
        "scale": axis_scale,
        # filter: drop overlapping tick labels (declutters dense log axes)
        "labels": {"show": True, "rotate": 0, "filter": True, "truncate": 100},
        "title": {"text": title},
    }


def series_vis(
    chart_type: str,
    series: list[tuple[str, str, str | None, str, str]],
    *,
    split_terms: str | None = None,
    scale: str = "linear",
    right_axis_title: str | None = None,
    y_min: float | None = None,
) -> dict:
    """A timeseries chart over @timestamp.

    ``series`` = [(agg_id, agg_type, field, label, axis), ...] where ``axis`` is
    "left" or "right". ``split_terms`` adds a terms sub-bucket (one line per term).
    """
    aggs: list[dict] = []
    series_params: list[dict] = []
    for agg_id, agg_type, field, label, axis in series:
        params = {"field": field} if field else {}
        aggs.append(
            {
                "id": agg_id,
                "enabled": True,
                "type": agg_type,
                "schema": "metric",
                "params": {**params, "customLabel": label},
            }
        )
        series_params.append(
            {
                "show": True,
                "type": chart_type,
                "mode": "normal",
                "data": {"label": label, "id": agg_id},
                "valueAxis": "ValueAxis-1" if axis == "left" else "ValueAxis-2",
                "drawLinesBetweenPoints": True,
                "lineWidth": 2,
                "showCircles": False,
                "interpolate": "linear",
            }
        )

    aggs.append(
        {
            "id": "date",
            "enabled": True,
            "type": "date_histogram",
            "schema": "segment",
            "params": {"field": "@timestamp", "interval": "auto", "min_doc_count": 1},
        }
    )
    if split_terms:
        aggs.append(
            {
                "id": "split",
                "enabled": True,
                "type": "terms",
                "schema": "group",
                "params": {
                    "field": split_terms,
                    "size": 12,
                    "order": "desc",
                    "orderBy": "_key",
                },
            }
        )

    value_axes = [_value_axis("ValueAxis-1", "left", "", scale, y_min)]
    if right_axis_title is not None:
        value_axes.append(_value_axis("ValueAxis-2", "right", right_axis_title, "linear"))

    return {
        "title": "",
        "type": chart_type,
        "aggs": aggs,
        "params": {
            "type": chart_type,
            "grid": {"categoryLines": False},
            "categoryAxes": [_category_axis()],
            "valueAxes": value_axes,
            "seriesParams": series_params,
            "addTooltip": True,
            "addLegend": True,
            "legendPosition": "right",
            "times": [],
            "addTimeMarker": False,
            "labels": {},
            "thresholdLine": {
                "show": False,
                "value": 10,
                "width": 1,
                "style": "full",
                "color": "#E7664C",
            },
        },
    }


def table_vis(metrics: list[tuple[str, str, str | None, str]], bucket: dict) -> dict:
    """A data table. ``metrics`` = [(agg_id, agg_type, field, label), ...]; ``bucket``
    is one bucket agg dict (terms / date_histogram)."""
    aggs = []
    for agg_id, agg_type, field, label in metrics:
        params = {"field": field} if field else {}
        aggs.append(
            {
                "id": agg_id,
                "enabled": True,
                "type": agg_type,
                "schema": "metric",
                "params": {**params, "customLabel": label},
            }
        )
    aggs.append(bucket)
    return {
        "title": "",
        "type": "table",
        "aggs": aggs,
        "params": {
            "perPage": 10,
            "showPartialRows": False,
            "showMetricsAtAllLevels": False,
            "showTotal": False,
            "totalFunc": "sum",
            "percentageCol": "",
        },
    }


def terms_bucket(field: str, label: str, size: int = 15, order_by: str = "1") -> dict:
    return {
        "id": "bucket",
        "enabled": True,
        "type": "terms",
        "schema": "bucket",
        "params": {
            "field": field,
            "size": size,
            "order": "desc",
            "orderBy": order_by,
            "customLabel": label,
        },
    }


def markdown_vis(text: str) -> dict:
    return {
        "title": "",
        "type": "markdown",
        "params": {"markdown": text, "openLinksInNewTab": True, "fontSize": 12},
        "aggs": [],
    }


def markdown(obj_id: str, title: str, text: str) -> dict:
    return {
        "id": obj_id,
        "type": "visualization",
        "attributes": {
            "title": title,
            "description": "",
            "uiStateJSON": "{}",
            "version": 1,
            "visState": json.dumps(markdown_vis(text)),
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {"query": {"query": "", "language": "kuery"}, "filter": []}
                )
            },
        },
        "references": [],
        "coreMigrationVersion": KIBANA_VERSION,
    }


def dashboard(
    obj_id: str,
    title: str,
    description: str,
    panels: list[tuple],
    *,
    time_from: str = "now-7d",
) -> dict:
    """``panels`` = [(viz_id, x, y, w, h[, time_from]), ...] on Kibana's 48-column
    grid. An optional 6th element pins that panel to its own ``[time_from, now]``
    range — used to keep short-window metric feeds full on a wide-window dashboard.
    """
    panels_json = []
    references = []
    for i, panel in enumerate(panels):
        viz_id, x, y, w, h = panel[:5]
        panel_index = str(i)
        ref_name = f"panel_{i}"
        embeddable: dict = {"enhancements": {}}
        if len(panel) > 5 and panel[5]:
            embeddable["timeRange"] = {"from": panel[5], "to": "now"}
        panels_json.append(
            {
                "version": KIBANA_VERSION,
                "type": "visualization",
                "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
                "panelIndex": panel_index,
                "embeddableConfig": embeddable,
                "panelRefName": ref_name,
            }
        )
        references.append({"name": ref_name, "type": "visualization", "id": viz_id})
    return {
        "id": obj_id,
        "type": "dashboard",
        "attributes": {
            "title": title,
            "description": description,
            "panelsJSON": json.dumps(panels_json),
            "optionsJSON": json.dumps(
                {"useMargins": True, "syncColors": False, "hidePanelTitles": False}
            ),
            "version": 1,
            "timeRestore": True,
            "timeFrom": time_from,
            "timeTo": "now",
            "refreshInterval": {"pause": True, "value": 60000},
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {"query": {"query": "", "language": "kuery"}, "filter": []}
                )
            },
        },
        "references": references,
        "coreMigrationVersion": KIBANA_VERSION,
    }


# --- the actual objects ----------------------------------------------------


def build() -> list[dict]:
    objects: list[dict] = [
        data_view(
            EVENTS_DV,
            "space-weather-events",
            field_formats={
                "metrics.proton_flux_10mev": {"id": "number", "params": {"pattern": "0,0.[00]"}},
                "xray_flux_uwm2": {"id": "number", "params": {"pattern": "0,0.[00]"}},
            },
            # X-ray flux is ~1e-6 W/m² — too tiny for Kibana's number formatter
            # (renders as 0). Expose it in µW/m² (x1e6) so values are normal-sized
            # and flare classes fall on round powers of ten (C=1, M=10, X=100).
            runtime_fields={
                "xray_flux_uwm2": {
                    "type": "double",
                    "script": {
                        "source": (
                            "if (!doc['metrics.xray_flux'].empty) "
                            "{ emit(doc['metrics.xray_flux'].value * 1000000) }"
                        )
                    },
                }
            },
        ),
        data_view(ALERTS_DV, "space-weather-alerts"),
    ]

    # SOC Overview ----------------------------------------------------------
    objects += [
        markdown(
            "sws-ov-header",
            "SOC Overview — header",
            "## 🛰️ Space-Weather SOC Overview\n"
            "Open detection alerts, current NOAA G/R/S scales, and event volume. "
            "Space weather is usually quiet — empty alert panels mean *all clear*.",
        ),
        viz(
            "sws-ov-open-alerts",
            "Open Alerts",
            metric_vis([("count", None, "Open alerts")]),
            ALERTS_DV,
            kql='alert.status : "active"',
        ),
        viz(
            "sws-ov-max-sev",
            "Highest Open Severity",
            metric_vis([("max", "event.severity", "Max severity (0-5)")]),
            ALERTS_DV,
            kql='alert.status : "active"',
        ),
        viz(
            "sws-ov-noaa-scales",
            "NOAA Scales — peak in range (G/R/S)",
            metric_vis(
                [
                    ("max", "metrics.g_scale", "G (geomagnetic)"),
                    ("max", "metrics.r_scale", "R (radio)"),
                    ("max", "metrics.s_scale", "S (radiation)"),
                ]
            ),
            EVENTS_DV,
            kql='event.dataset : "swpc.noaa_scales"',
        ),
        viz(
            "sws-ov-alerts-by-sev",
            "Open Alerts by Severity",
            series_vis(
                "histogram",
                [("1", "count", None, "Alerts", "left")],
                split_terms="event.severity",
            ),
            ALERTS_DV,
            kql='alert.status : "active"',
        ),
        viz(
            "sws-ov-event-volume",
            "Event Volume by Category",
            series_vis(
                "histogram",
                [("1", "count", None, "Events", "left")],
                split_terms="event.category",
            ),
            EVENTS_DV,
        ),
        viz(
            "sws-ov-recent-alerts",
            "Recent Alerts",
            table_vis(
                [("1", "max", "event.severity", "Max severity"), ("2", "count", None, "Count")],
                terms_bucket("rule.name", "Rule"),
            ),
            ALERTS_DV,
        ),
    ]
    overview = dashboard(
        "sws-dashboard-overview",
        "SOC Overview",
        "Open alerts by severity, current NOAA scales, and event volume timeline.",
        [
            ("sws-ov-header", 0, 0, 48, 6),
            ("sws-ov-open-alerts", 0, 6, 12, 8),
            ("sws-ov-max-sev", 12, 6, 12, 8),
            ("sws-ov-noaa-scales", 24, 6, 24, 8),
            ("sws-ov-alerts-by-sev", 0, 14, 24, 12),
            ("sws-ov-event-volume", 24, 14, 24, 12),
            ("sws-ov-recent-alerts", 0, 26, 48, 12),
        ],
    )

    # Geomagnetic -----------------------------------------------------------
    objects += [
        viz(
            "sws-geo-kp-now",
            "Peak Kp (range)",
            metric_vis([("max", "metrics.kp_index", "Peak Kp")]),
            EVENTS_DV,
            kql='event.dataset : "swpc.planetary_k_index"',
        ),
        viz(
            "sws-geo-kp-history",
            "Planetary K-index",
            series_vis("histogram", [("1", "max", "metrics.kp_index", "Kp", "left")]),
            EVENTS_DV,
            kql='event.dataset : "swpc.planetary_k_index"',
        ),
        viz(
            "sws-geo-bz-bt",
            "IMF Bz / Bt (nT)",
            series_vis(
                "line",
                [
                    ("1", "min", "metrics.bz_gsm", "Bz (min)", "left"),
                    ("2", "max", "metrics.bt", "Bt (max)", "left"),
                ],
            ),
            EVENTS_DV,
            kql='event.dataset : "swpc.solar_wind_mag"',
        ),
        viz(
            "sws-geo-wind",
            "Solar Wind Speed & Density",
            series_vis(
                "line",
                [
                    ("1", "max", "metrics.speed_km_s", "Speed km/s", "left"),
                    ("2", "avg", "metrics.density", "Density p/cc", "right"),
                ],
                right_axis_title="Density (p/cc)",
            ),
            EVENTS_DV,
            kql='event.dataset : "swpc.solar_wind_plasma"',
        ),
    ]
    geomagnetic = dashboard(
        "sws-dashboard-geomagnetic",
        "Geomagnetic",
        "Kp index history, interplanetary magnetic field (Bz/Bt), and solar wind.",
        [
            ("sws-geo-kp-now", 0, 0, 12, 8),
            ("sws-geo-kp-history", 12, 0, 36, 8),
            ("sws-geo-bz-bt", 0, 8, 24, 13),
            ("sws-geo-wind", 24, 8, 24, 13),
        ],
    )

    # Solar Activity --------------------------------------------------------
    objects += [
        viz(
            "sws-sol-xray",
            "GOES X-ray Flux — long band (µW/m², log)",
            series_vis(
                "line",
                [("1", "max", "xray_flux_uwm2", "X-ray flux (µW/m²)", "left")],
                scale="log",
                y_min=0.1,  # quiet background ~0.5 µW/m²; C=1, M=10, X=100, replay X10=1000
            ),
            EVENTS_DV,
            kql='event.dataset : "swpc.goes_xray"',
        ),
        viz(
            "sws-sol-protons",
            "GOES Integral Protons ≥10 MeV (pfu, log)",
            series_vis(
                "line",
                [("1", "max", "metrics.proton_flux_10mev", "Proton flux", "left")],
                scale="log",
                y_min=0.01,  # quiet background is ~0.2 pfu (< 1); floor below it
            ),
            EVENTS_DV,
            kql='event.dataset : "swpc.goes_protons"',
        ),
        viz(
            "sws-sol-donki",
            "DONKI Flares & CMEs",
            series_vis(
                "histogram",
                [("1", "count", None, "Events", "left")],
                split_terms="event.dataset",
            ),
            EVENTS_DV,
            kql='event.dataset : "donki.flr" or event.dataset : "donki.cme"',
        ),
        viz(
            "sws-sol-flares",
            "Recent Solar Events (DONKI)",
            table_vis(
                [("1", "max", "event.severity", "Max severity"), ("2", "count", None, "Count")],
                terms_bucket("event.dataset", "Catalog"),
            ),
            EVENTS_DV,
            kql='event.dataset : "donki.flr" or event.dataset : "donki.cme" '
            'or event.dataset : "donki.sep"',
        ),
    ]
    solar = dashboard(
        "sws-dashboard-solar",
        "Solar Activity",
        "X-ray flux (log) and proton flux with DONKI flare/CME catalog activity.",
        [
            # X-ray/proton feeds only have a 7-day window, so pin those panels to it
            # while the dashboard (and the DONKI panels) span a richer 30 days.
            ("sws-sol-xray", 0, 0, 24, 13, "now-7d"),
            ("sws-sol-protons", 24, 0, 24, 13, "now-7d"),
            ("sws-sol-donki", 0, 13, 24, 12),
            ("sws-sol-flares", 24, 13, 24, 12),
        ],
        time_from="now-30d",
    )

    # Pipeline Health -------------------------------------------------------
    objects += [
        viz(
            "sws-health-total",
            "Total Events (range)",
            metric_vis([("count", None, "Events ingested")]),
            EVENTS_DV,
        ),
        viz(
            "sws-health-feeds",
            "Documents per Feed",
            series_vis(
                "histogram",
                [("1", "count", None, "Docs", "left")],
                split_terms="source.feed",
            ),
            EVENTS_DV,
        ),
        viz(
            "sws-health-lastseen",
            "Feed Last-Seen (feed-down check)",
            table_vis(
                [("1", "max", "@timestamp", "Last document"), ("2", "count", None, "Docs")],
                terms_bucket("source.feed", "Feed", size=20, order_by="2"),
            ),
            EVENTS_DV,
        ),
        viz(
            "sws-health-by-dataset",
            "Ingest by Dataset",
            table_vis(
                [("1", "count", None, "Docs")],
                terms_bucket("event.dataset", "Dataset", size=20, order_by="1"),
            ),
            EVENTS_DV,
        ),
    ]
    health = dashboard(
        "sws-dashboard-health",
        "Pipeline Health",
        "Ingest volume per feed and last-seen times — the SIEM 'log source health' view.",
        [
            ("sws-health-total", 0, 0, 12, 8),
            ("sws-health-feeds", 12, 0, 36, 13),
            ("sws-health-lastseen", 0, 8, 24, 13),
            ("sws-health-by-dataset", 24, 13, 24, 13),
        ],
    )

    objects += [overview, geomagnetic, solar, health]
    return objects


def main() -> None:
    objects = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        for obj in objects:
            fh.write(json.dumps(obj) + "\n")
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj["type"]] = counts.get(obj["type"], 0) + 1
    summary = ", ".join(f"{n} {t}" for t, n in sorted(counts.items()))
    print(f"Wrote {len(objects)} saved objects ({summary}) -> {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
