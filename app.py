"""Vercel entrypoint — single FastAPI app exposing 3 SVG endpoints.

Vercel auto-detects `app.py` with a top-level `app` variable as the ASGI
entrypoint. Routes mirror what the README documents.
"""

from __future__ import annotations

import sys
import traceback

from fastapi import FastAPI, Query, Response

from lib.github import fetch, language_percentages
from lib.render import cache_headers, env_username, render
from lib.theme import DARK

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# ---- Stats card ------------------------------------------------------------

ICONS = {
    "star": '<path d="M8 1.5l2.06 4.18 4.61.67-3.34 3.25.79 4.59L8 11.93 3.88 14.19l.79-4.59L1.33 6.35l4.61-.67L8 1.5z"/>',
    "fork": '<circle cx="4" cy="3" r="1.6"/><circle cx="12" cy="3" r="1.6"/><circle cx="8" cy="13" r="1.6"/><path d="M4 4.6v2.2a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V4.6M8 8.8v2.6"/>',
    "commit": '<circle cx="8" cy="8" r="2.5"/><path d="M1.5 8h4M10.5 8h4"/>',
    "pr": '<circle cx="4" cy="3.5" r="1.4"/><circle cx="4" cy="12.5" r="1.4"/><circle cx="12" cy="12.5" r="1.4"/><path d="M4 4.9v6.2M12 11.1V7a2 2 0 0 0-2-2H7.5l1.5-1.5M9 6.5L7.5 5"/>',
    "issue": '<circle cx="8" cy="8" r="6.5"/><circle cx="8" cy="8" r="1.5"/>',
    "review": '<path d="M2 3h12v8H9l-2 2-2-2H2z"/><path d="M5.5 7l1.5 1.5 3-3"/>',
    "people": '<circle cx="6" cy="6" r="2.5"/><path d="M2 13c0-2.2 1.8-4 4-4s4 1.8 4 4M11 9.5a2 2 0 1 0 0-3M14 13c0-1.7-1-3.1-2.5-3.7"/>',
    "repo": '<path d="M3 1.5h9.5v13H3a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1z"/><path d="M3 11.5h9.5"/>',
}


def _error_response(message: bytes) -> Response:
    return Response(content=message, status_code=500, media_type="text/plain")


@app.get("/api/stats")
def stats(username: str | None = Query(default=None)):
    try:
        login = env_username(username)
        data = fetch(login)

        rows = [
            {"icon": ICONS["star"], "label": "Stars", "value": f"{data.total_stars}"},
            {"icon": ICONS["fork"], "label": "Forks", "value": f"{data.total_forks}"},
            {"icon": ICONS["commit"], "label": "Commits (this year)", "value": f"{data.total_commits}"},
            {"icon": ICONS["pr"], "label": "Pull requests merged", "value": f"{data.merged_prs}"},
            {"icon": ICONS["issue"], "label": "Issues closed", "value": f"{data.closed_issues}"},
            {"icon": ICONS["review"], "label": "Code reviews", "value": f"{data.reviews}"},
            {"icon": ICONS["people"], "label": "Followers", "value": f"{data.followers}"},
            {"icon": ICONS["repo"], "label": "Repositories", "value": f"{data.public_repos}"},
        ]

        svg = render(
            "stats.svg.j2",
            title=f"{data.name}'s Statistics",
            width=460,
            height=300,
            rows=rows,
        )
        return Response(content=svg, headers=cache_headers())
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return _error_response(b"failed to render stats")


# ---- Languages card --------------------------------------------------------


@app.get("/api/languages")
def languages(
    username: str | None = Query(default=None),
    metric: str = Query(default="size"),
):
    try:
        login = env_username(username)
        metric_norm = metric.lower() if metric.lower() in ("size", "commits") else "size"

        data = fetch(login)
        source = (
            data.languages_by_size if metric_norm == "size" else data.languages_by_commits
        )
        ranked = language_percentages(source, metric=metric_norm, limit=10)

        items = [
            {
                "name": stat.name,
                "color": stat.color or DARK.fallback_lang,
                "pct": pct,
            }
            for stat, pct in ranked
        ]

        metric_label = "File Size" if metric_norm == "size" else "Commits"

        svg = render(
            "languages.svg.j2",
            width=460,
            height=300,
            items=items,
            metric_label=metric_label,
        )
        return Response(content=svg, headers=cache_headers())
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return _error_response(b"failed to render languages")


# ---- Activity hero ---------------------------------------------------------


def _level(count: int, p99: int) -> int:
    if count <= 0:
        return 0
    if p99 <= 0:
        return 1
    ratio = count / p99
    if ratio < 0.25:
        return 1
    if ratio < 0.5:
        return 2
    if ratio < 0.75:
        return 3
    return 4


def _build_heatmap(contribution_days: list[int], offset: int) -> list[dict]:
    if not contribution_days:
        return []

    p99 = max(contribution_days) or 1
    cells: list[dict] = []
    idx = 0
    week_count = (offset + len(contribution_days) + 6) // 7
    for col in range(week_count):
        for row in range(7):
            position = col * 7 + row
            if position < offset:
                continue
            if idx >= len(contribution_days):
                break
            count = contribution_days[idx]
            cells.append(
                {
                    "col": col,
                    "row": row,
                    "level": _level(count, p99),
                    "delay": round(0.001 * idx, 3),
                    "tooltip": f"{count} contribution{'s' if count != 1 else ''}",
                }
            )
            idx += 1
    return cells


@app.get("/api/activity")
def activity(username: str | None = Query(default=None)):
    try:
        from datetime import datetime

        login = env_username(username)
        data = fetch(login)
        cells = _build_heatmap(data.contribution_days, data.contribution_offset)

        metrics = [
            {"value": f"{data.contributions_year:,}", "label": "Contributions"},
            {"value": f"{data.total_commits:,}", "label": "Commits"},
            {"value": str(data.current_streak), "label": "Current streak"},
            {"value": str(data.longest_streak), "label": "Longest streak"},
            {"value": str(data.followers), "label": "Followers"},
            {"value": str(data.public_repos), "label": "Repositories"},
        ]

        svg = render(
            "activity.svg.j2",
            title=f"{data.name}'s Activity",
            subtitle=f"@{data.login}  ·  {data.contributions_year:,} contributions in the last year",
            width=940,
            height=280,
            metrics=metrics,
            heatmap_cells=cells,
            year_label=str(datetime.now().year),
        )
        return Response(content=svg, headers=cache_headers())
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return _error_response(b"failed to render activity")


@app.get("/")
def root():
    return Response(
        content=(
            "github-profile-stats — endpoints:\n"
            "  /api/activity\n"
            "  /api/stats\n"
            "  /api/languages?metric=size|commits\n"
        ),
        media_type="text/plain",
    )
