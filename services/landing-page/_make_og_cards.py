"""Generate Open Graph social cards for AgentShield pages.

Produces 1200x630 PNG cards for each public page using the canonical dark theme.
Run with:
    python3 _make_og_cards.py
Outputs land in ./og/<page>.png and ./og/<page>.svg.
"""

from __future__ import annotations

import os
from pathlib import Path

import cairosvg

HERE = Path(__file__).parent
OUT_DIR = HERE / "og"
OUT_DIR.mkdir(exist_ok=True)


BRAND_BG = "#0a0a0f"
BRAND_SURFACE = "#12121a"
BRAND_BORDER = "#1e1e2e"
BRAND_ACCENT = "#6366f1"
BRAND_ACCENT2 = "#818cf8"
BRAND_TEXT = "#e4e4e7"
BRAND_MUTED = "#a1a1aa"
BRAND_GREEN = "#22c55e"


def shield_icon_path(cx: float, cy: float, size: float) -> str:
    """Return an SVG <path> d-string of a shield glyph centered on (cx, cy)."""
    s = size / 2
    # Simple shield: rounded top, V bottom
    return (
        f"M{cx - s},{cy - s} "
        f"C{cx - s},{cy - s * 0.4} {cx - s},{cy + s * 0.3} {cx},{cy + s} "
        f"C{cx + s},{cy + s * 0.3} {cx + s},{cy - s * 0.4} {cx + s},{cy - s} "
        f"C{cx + s * 0.4},{cy - s * 0.8} {cx - s * 0.4},{cy - s * 0.8} {cx - s},{cy - s} Z"
    )


def og_card(
    *,
    eyebrow: str,
    title: str,
    subtitle: str,
    accent_chip: str | None = None,
    stat: tuple[str, str] | None = None,
) -> str:
    """Compose the OG card SVG. title can include a literal newline to break lines."""
    title_lines = title.split("\n")
    if len(title_lines) == 1:
        line_ys = [330]
    elif len(title_lines) == 2:
        line_ys = [300, 388]
    else:
        line_ys = [270, 352, 434]

    # Title tspans
    title_tspans = "".join(
        f'<tspan x="80" y="{y}">{line}</tspan>' for line, y in zip(title_lines, line_ys)
    )

    chip_svg = ""
    if accent_chip:
        chip_svg = f"""
        <g transform="translate(80, 180)">
          <rect rx="999" ry="999" x="0" y="0" width="{20 + 11 * len(accent_chip)}" height="38"
                fill="{BRAND_ACCENT}" fill-opacity="0.14" stroke="{BRAND_ACCENT}" stroke-opacity="0.45"/>
          <circle cx="20" cy="19" r="4" fill="{BRAND_ACCENT2}"/>
          <text x="34" y="25" fill="{BRAND_ACCENT2}"
                font-family="Inter, system-ui, sans-serif" font-size="15" font-weight="600"
                letter-spacing="0.08em" text-transform="uppercase">{accent_chip}</text>
        </g>
        """

    stat_svg = ""
    if stat:
        value, label = stat
        stat_svg = f"""
        <g transform="translate(820, 200)">
          <rect x="0" y="0" width="300" height="200" rx="20" ry="20"
                fill="{BRAND_SURFACE}" stroke="{BRAND_BORDER}"/>
          <text x="150" y="108" fill="{BRAND_ACCENT2}" text-anchor="middle"
                font-family="'JetBrains Mono', monospace" font-size="64" font-weight="700">
            {value}
          </text>
          <text x="150" y="150" fill="{BRAND_MUTED}" text-anchor="middle"
                font-family="Inter, system-ui, sans-serif" font-size="16" font-weight="500"
                letter-spacing="0.1em" text-transform="uppercase">
            {label}
          </text>
        </g>
        """

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BRAND_BG}"/>
      <stop offset="100%" stop-color="#0e0e18"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.2" cy="0.2" r="0.8">
      <stop offset="0%" stop-color="{BRAND_ACCENT}" stop-opacity="0.28"/>
      <stop offset="70%" stop-color="{BRAND_ACCENT}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{BRAND_ACCENT}" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="{BRAND_ACCENT2}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <!-- background -->
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#glow)"/>

  <!-- decorative grid -->
  <g stroke="{BRAND_BORDER}" stroke-width="1" opacity="0.6">
    <line x1="0" y1="80" x2="1200" y2="80"/>
    <line x1="0" y1="550" x2="1200" y2="550"/>
  </g>

  <!-- logo lockup -->
  <g transform="translate(80, 110)">
    <path d="{shield_icon_path(20, 20, 36)}" fill="{BRAND_ACCENT}" fill-opacity="0.2"
          stroke="{BRAND_ACCENT}" stroke-width="2"/>
    <path d="M12,18 L18,24 L30,12" fill="none" stroke="{BRAND_ACCENT2}" stroke-width="3"
          stroke-linecap="round" stroke-linejoin="round"/>
    <text x="56" y="27" fill="{BRAND_TEXT}"
          font-family="Inter, system-ui, sans-serif" font-size="22" font-weight="700"
          letter-spacing="-0.01em">
      AgentShield
    </text>
  </g>

  <!-- eyebrow -->
  <text x="80" y="158" fill="{BRAND_MUTED}"
        font-family="'JetBrains Mono', monospace" font-size="15" font-weight="500"
        letter-spacing="0.22em" text-transform="uppercase">
    {eyebrow}
  </text>

  {chip_svg}

  <!-- accent rule -->
  <rect x="80" y="225" width="120" height="4" rx="2" fill="url(#rule)"/>

  <!-- title -->
  <text fill="{BRAND_TEXT}"
        font-family="Inter, system-ui, sans-serif" font-size="66" font-weight="700"
        letter-spacing="-0.02em">
    {title_tspans}
  </text>

  {stat_svg}

  <!-- subtitle -->
  <text x="80" y="500" fill="{BRAND_MUTED}"
        font-family="Inter, system-ui, sans-serif" font-size="24" font-weight="400"
        letter-spacing="0">
    {subtitle}
  </text>

  <!-- footer -->
  <g transform="translate(80, 570)">
    <circle cx="6" cy="-5" r="5" fill="{BRAND_GREEN}"/>
    <text x="22" y="0" fill="{BRAND_MUTED}"
          font-family="Inter, system-ui, sans-serif" font-size="18" font-weight="500">
      agentshield.dev
    </text>
    <text x="1040" y="0" fill="{BRAND_MUTED}" text-anchor="end"
          font-family="'JetBrains Mono', monospace" font-size="15" font-weight="500"
          letter-spacing="0.12em" text-transform="uppercase">
      LLM · Security · API
    </text>
  </g>
</svg>
"""


CARDS: dict[str, dict] = {
    "og-default": dict(
        eyebrow="Prompt-Injection Detection API",
        title="Stop prompt injections\nbefore they hit your LLM.",
        subtitle="Sub-20ms classifier · 99.4% recall · 100 free requests/day.",
        accent_chip="AgentShield · v1",
    ),
    "og-benchmark": dict(
        eyebrow="Benchmark Report · April 2026",
        title="99.4% recall across\n4 public datasets.",
        subtitle="Tested on 12,000 prompts. Median latency 14ms. Full methodology online.",
        accent_chip="Benchmark · Public",
        stat=("99.4%", "Recall"),
    ),
    "og-blog": dict(
        eyebrow="AgentShield Blog",
        title="Writing about\nLLM security.",
        subtitle="Benchmarks, threat models, and lessons from shipping prompt-injection defenses.",
        accent_chip="Blog",
    ),
    "og-compare": dict(
        eyebrow="Compare · Independent view",
        title="AgentShield vs.\nthe field.",
        subtitle="Latency, recall, price, deployment — side by side. No logos in tier, just data.",
        accent_chip="Comparison",
    ),
    "og-status": dict(
        eyebrow="Live System Status",
        title="Uptime, latency,\nand recent checks.",
        subtitle="Updated every 60 seconds · Frankfurt region · 40-day history window.",
        accent_chip="Status · Live",
        stat=("99.98%", "30-day uptime"),
    ),
    "og-signup": dict(
        eyebrow="Get an API key",
        title="Free tier.\nNo credit card.",
        subtitle="100 classifications/day · upgrade to 50,000/day when you need it.",
        accent_chip="Sign up · Free",
    ),
    "og-pricing": dict(
        eyebrow="Pricing · Simple tiers",
        title="Free, Dev, Pro,\nor Enterprise.",
        subtitle="Start free. Scale to 50,000/day for $99. Self-host when you outgrow us.",
        accent_chip="Pricing",
    ),
}


def main() -> None:
    for slug, kw in CARDS.items():
        svg = og_card(**kw)
        svg_path = OUT_DIR / f"{slug}.svg"
        png_path = OUT_DIR / f"{slug}.png"
        svg_path.write_text(svg, encoding="utf-8")
        cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            write_to=str(png_path),
            output_width=1200,
            output_height=630,
        )
        print(f"wrote {svg_path.name} + {png_path.name}  ({os.path.getsize(png_path)} bytes)")


if __name__ == "__main__":
    main()
