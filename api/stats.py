"""GET /api/stats — Statistics card.

Renders the bottom-left card: stars, forks, commits, PRs, issues, reviews,
followers, and repositories with contributions.
"""

from __future__ import annotations

import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Vercel Python runtime: the project root is on sys.path
from lib.github import fetch
from lib.render import cache_headers, env_username, render

# Stroke-only SVG icons rendered inline. Designed at 16x16, drawn with
# `stroke="currentColor"` via the .icon class.
ICONS = {
    "star": '<path d="M8 1.5l2.06 4.18 4.61.67-3.34 3.25.79 4.59L8 11.93 3.88 14.19l.79-4.59L1.33 6.35l4.61-.67L8 1.5z"/>',
    "fork": '<circle cx="4" cy="3" r="1.6"/><circle cx="12" cy="3" r="1.6"/><circle cx="8" cy="13" r="1.6"/><path d="M4 4.6v2.2a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V4.6M8 8.8v2.6"/>',
    "commit": '<circle cx="8" cy="8" r="2.5"/><path d="M1.5 8h4M10.5 8h4"/>',
    "pr": '<circle cx="4" cy="3.5" r="1.4"/><circle cx="4" cy="12.5" r="1.4"/><circle cx="12" cy="12.5" r="1.4"/><path d="M4 4.9v6.2M12 11.1V7a2 2 0 0 0-2-2H7.5l1.5-1.5M9 6.5L7.5 5"/>',
    "issue": '<circle cx="8" cy="8" r="6.5"/><circle cx="8" cy="8" r="1.5"/>',
    "review": '<path d="M2 3h12v8H9l-2 2-2-2H2z"/><path d="M5.5 7l1.5 1.5 3-3"/>',
    "people": '<circle cx="6" cy="6" r="2.5"/><path d="M2 13c0-2.2 1.8-4 4-4s4 1.8 4 4M11 9.5a2 2 0 1 0 0-3M14 13c0-1.7-1-3.1-2.5-3.7"/>',
    "repo": '<path d="M3 1.5h9.5v13H3a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1z"/><path d="M3 11.5h9.5"/>',
    "lines": '<path d="M2 4h12M2 8h12M2 12h8"/>',
    "eye": '<path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — required by BaseHTTPRequestHandler
        try:
            qs = parse_qs(urlparse(self.path).query)
            username = env_username(qs.get("username", [None])[0])
            data = fetch(username)

            rows = [
                {"icon": ICONS["star"], "label": "Stars", "value": f"{data.total_stars}"},
                {"icon": ICONS["fork"], "label": "Forks", "value": f"{data.total_forks}"},
                {"icon": ICONS["commit"], "label": "Commits (this year)", "value": f"{data.total_commits}"},
                {"icon": ICONS["pr"], "label": "Pull requests merged", "value": f"{data.merged_prs}"},
                {"icon": ICONS["issue"], "label": "Issues closed", "value": f"{data.closed_issues}"},
                {"icon": ICONS["review"], "label": "Code reviews", "value": f"{data.reviews}"},
                {"icon": ICONS["people"], "label": "Followers", "value": f"{data.followers}"},
                {"icon": ICONS["repo"], "label": "Public repositories", "value": f"{data.public_repos}"},
            ]

            height = 70 + 28 * len(rows) + 18

            svg = render(
                "stats.svg.j2",
                title=f"{data.name}'s Statistics",
                width=460,
                height=height,
                rows=rows,
            )

            body = svg.encode("utf-8")
            self.send_response(200)
            for k, v in cache_headers().items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:  # noqa: BLE001 — surface message in dev, generic in prod
            traceback.print_exc(file=sys.stderr)
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"failed to render stats")
