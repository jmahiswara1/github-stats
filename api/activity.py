"""GET /api/activity — Activity hero card.

Wide top card with contribution heatmap (last 52 weeks), headline metrics,
and streak info.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from lib.github import fetch
from lib.render import cache_headers, env_username, render


def _level(count: int, p99: int) -> int:
    """Map a daily contribution count onto the 5-level GitHub scale."""
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


def _build_heatmap(
    contribution_days: list[int], offset: int
) -> tuple[list[dict], list[dict]]:
    """Convert flat day list to (cells, month_labels).

    The contributions array starts on a calendar week boundary (Sunday) but the
    user's first day in that week may be any weekday, hence the offset. We pad
    the first column with empty cells for missing leading days.
    """
    if not contribution_days:
        return [], []

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

    return cells, []


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        try:
            qs = parse_qs(urlparse(self.path).query)
            username = env_username(qs.get("username", [None])[0])
            data = fetch(username)

            cells, _ = _build_heatmap(data.contribution_days, data.contribution_offset)

            metrics = [
                {"value": f"{data.contributions_year:,}", "label": "Contributions"},
                {"value": f"{data.total_commits:,}", "label": "Commits"},
                {"value": str(data.current_streak), "label": "Current streak"},
                {"value": str(data.longest_streak), "label": "Longest streak"},
                {"value": str(data.followers), "label": "Followers"},
                {"value": str(data.public_repos), "label": "Repositories"},
            ]

            year = datetime.now().year
            svg = render(
                "activity.svg.j2",
                title=f"{data.name}'s Activity",
                subtitle=f"@{data.login}  ·  {data.contributions_year:,} contributions in the last year",
                width=940,
                height=260,
                metrics=metrics,
                heatmap_cells=cells,
                year_label=str(year),
            )

            body = svg.encode("utf-8")
            self.send_response(200)
            for k, v in cache_headers().items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"failed to render activity")
