"""Design tokens for the README charts.

Two selected modes, not one palette with an automatic flip. The categorical hues
are the validated default order; the dark column is the same hues re-stepped for
the dark surface. Both were run through the palette validator before use:

  light  worst adjacent CVD dE 9.1, normal-vision dE 22.9 - PASS
         (aqua and yellow sit under 3:1 on the light surface, so every segment
          carries a visible direct label; that is the documented relief.)
  dark   worst adjacent CVD dE 8.4, normal-vision dE 19.8 - PASS

These charts are static SVG in a README: no hover layer is possible, so direct
labels are not optional here, they are the only labelling there is.
"""

LIGHT = {
    "name": "light",
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "ink3": "#7d7c75",
    "grid": "#e6e4dd",
    "track": "#eceae3",
    "muted": "#c4c2b8",
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
    "accent": "#2a78d6",
    "critical": "#d03b3b",
    "serious": "#ec835a",
    "good": "#0ca30c",
}

DARK = {
    "name": "dark",
    "surface": "#1a1a19",
    "ink": "#ffffff",
    "ink2": "#c3c2b7",
    "ink3": "#8f8e85",
    "grid": "#2f2f28",
    "track": "#26251f",
    "muted": "#55544c",
    "series": ["#3987e5", "#d95926", "#199e70", "#c98500"],
    "accent": "#3987e5",
    "critical": "#d03b3b",
    "serious": "#ec835a",
    "good": "#0ca30c",
}

THEMES = (LIGHT, DARK)

FONT = ('-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,'
        'Helvetica,Arial,sans-serif')
MONO = 'ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace'


def esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def text(x, y, s, *, size=13, fill="#000", weight=400, anchor="start",
         font=FONT, opacity=None, mono=False):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    ff = MONO if mono else font
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family=\'{ff}\' font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"'
            f'{op}>{esc(s)}</text>')


def rect(x, y, w, h, fill, *, r=4, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" '
            f'height="{max(h, 0):.1f}" rx="{r}" fill="{fill}"{op}/>')


def svg(width, height, theme, body, *, title="", desc=""):
    """Wrap chart body. Includes an accessible title/desc pair - a README image
    with no alternative text is unreadable to anyone using a screen reader."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-labelledby="t d" font-family=\'{FONT}\'>'
        f'<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>'
        f'<rect width="{width}" height="{height}" fill="{theme["surface"]}" rx="10"/>'
        f"{body}</svg>"
    )


def fmt(n) -> str:
    return f"{n:,}"
