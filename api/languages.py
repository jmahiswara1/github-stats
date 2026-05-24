"""GET /api/languages — Languages card.

Query params:
  metric=size      (default) percentages by file size
  metric=commits   percentages by commit count to repos using the language as primary
"""

from __future__ import annotations

import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from lib.github import fetch, language_percentages
from lib.render import cache_headers, env_username, render
from lib.theme import DARK


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        try:
            qs = parse_qs(urlparse(self.path).query)
            username = env_username(qs.get("username", [None])[0])
            metric = qs.get("metric", ["size"])[0].lower()
            if metric not in ("size", "commits"):
                metric = "size"

            data = fetch(username)
            source = (
                data.languages_by_size if metric == "size" else data.languages_by_commits
            )
            ranked = language_percentages(source, metric=metric, limit=10)

            items = []
            for stat, pct in ranked:
                items.append(
                    {
                        "name": stat.name,
                        "color": stat.color or DARK.fallback_lang,
                        "pct": pct,
                    }
                )

            metric_label = "File Size" if metric == "size" else "Commits"
            rows = (len(items) + 1) // 2
            height = 92 + rows * 22 + 16

            svg = render(
                "languages.svg.j2",
                width=460,
                height=height,
                items=items,
                metric_label=metric_label,
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
            self.wfile.write(b"failed to render languages")
