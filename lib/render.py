"""SVG rendering helpers — Jinja env, response headers, formatting."""

from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .theme import css_vars

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["svg", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _humanize(n: int | float) -> str:
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M")


def _percent(n: float, digits: int = 2) -> str:
    return f"{n:.{digits}f}%"


_env.filters["humanize"] = _humanize
_env.filters["percent"] = _percent


def render(template: str, **context) -> str:
    """Render an SVG template with theme CSS variables injected."""
    tmpl = _env.get_template(template)
    return tmpl.render(css_vars=css_vars(), **context)


def cache_headers(max_age: int = 21600) -> dict[str, str]:
    """6h browser cache, 6h CDN cache, allow stale-while-revalidate for 1d.

    GitHub camo strips most headers but Vercel's CDN honors s-maxage so origin
    hits stay rare. Once a deployment has warmed the cache, GitHub camo gets
    sub-second responses regardless of how many repos the user has.
    """
    return {
        "Content-Type": "image/svg+xml; charset=utf-8",
        "Cache-Control": (
            f"public, max-age={max_age}, "
            f"s-maxage={max_age}, "
            f"stale-while-revalidate={max_age * 4}"
        ),
        # CDN-Cache-Control overrides Cache-Control on Vercel's edge.
        # Setting to 7d so re-fetches hit Vercel cache, not GitHub API.
        "CDN-Cache-Control": "public, max-age=604800",
    }


def env_username(query_username: str | None) -> str:
    """Username precedence: ?username= query param > GH_USERNAME env."""
    if query_username:
        return query_username
    fallback = os.environ.get("GH_USERNAME", "")
    if not fallback:
        raise RuntimeError(
            "username is required: pass ?username=... or set GH_USERNAME"
        )
    return fallback
