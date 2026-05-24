"""Theme palettes for dark and light modes.

Both themes are exported as design tokens. The SVG embeds CSS variables and
uses `prefers-color-scheme` so a single SVG adapts to viewer's browser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    bg: str
    card_bg: str
    card_border: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_soft: str
    # Heatmap scale: 5 stops, idx 0 = empty, 4 = max
    heat: tuple[str, str, str, str, str]
    # Language palette fallback when GitHub doesn't expose a color
    fallback_lang: str


DARK = Theme(
    bg="#0d1117",
    card_bg="#161b22",
    card_border="#30363d",
    text_primary="#e6edf3",
    text_secondary="#9198a1",
    text_muted="#6e7681",
    accent="#58a6ff",
    accent_soft="#1f6feb",
    heat=("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
    fallback_lang="#8b949e",
)

LIGHT = Theme(
    bg="#ffffff",
    card_bg="#ffffff",
    card_border="#d0d7de",
    text_primary="#1f2328",
    text_secondary="#59636e",
    text_muted="#818b98",
    accent="#0969da",
    accent_soft="#218bff",
    heat=("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
    fallback_lang="#959da5",
)


def css_vars() -> str:
    """Emit `:root` and `@media (prefers-color-scheme: light)` overrides.

    Embedded inside `<style>` of the SVG so a single file handles both themes.
    """
    def block(theme: Theme) -> str:
        return (
            f"--bg:{theme.bg};"
            f"--card-bg:{theme.card_bg};"
            f"--card-border:{theme.card_border};"
            f"--text:{theme.text_primary};"
            f"--text-secondary:{theme.text_secondary};"
            f"--text-muted:{theme.text_muted};"
            f"--accent:{theme.accent};"
            f"--accent-soft:{theme.accent_soft};"
            f"--heat-0:{theme.heat[0]};"
            f"--heat-1:{theme.heat[1]};"
            f"--heat-2:{theme.heat[2]};"
            f"--heat-3:{theme.heat[3]};"
            f"--heat-4:{theme.heat[4]};"
        )

    return (
        f":root{{{block(DARK)}}}"
        f"@media (prefers-color-scheme: light){{:root{{{block(LIGHT)}}}}}"
    )


def resolve(theme_name: str | None) -> Theme:
    """Forced theme via query param. None means auto (use css_vars)."""
    if theme_name == "light":
        return LIGHT
    return DARK
