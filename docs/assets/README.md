# Generated assets

Nothing in this directory is drawn by hand. Every chart, the logo, the hero and the social
preview are generated from measured JSON, so a number in the README can never drift from the
measurement behind it. CI fails if a committed asset no longer matches its data.

```bash
python benchmarks/run.py             # refresh the measurements first
python docs/assets/make_charts.py    # six charts, light + dark
python docs/assets/make_brand.py     # logo, hero, social preview (SVG)
python docs/assets/make_terminal.py  # terminal demo, from a real CLI run
```

| File | Source of its numbers |
|---|---|
| `cost-model-*.svg` | `data/case-study.json` |
| `budget-*.svg` | `data/case-study.json` |
| `usage-*.svg` | `data/case-study.json` |
| `mcp-*.svg` | `data/case-study.json` |
| `savings-*.svg` | `data/case-study.json` |
| `tokenizer-*.svg` | `benchmarks/results/benchmark.json` |
| `terminal.svg` | a live `contextlint audit` run against `benchmarks/fixtures/bloated` |
| `hero-*.svg`, `social-*.svg`, `logo-*.svg` | both of the above |

`data/case-study.json` holds aggregates only — no file paths, no machine-specific content.

## Design

`theme.py` holds the tokens. The categorical hues are a validated order: worst adjacent
colour-vision-deficiency ΔE 9.1 light / 8.4 dark, worst adjacent normal-vision ΔE 22.9 / 19.8.
Two hues sit under 3:1 against the light surface, so every segment carries a visible direct
label — these are static images in a README, with no hover layer to fall back on.

Light and dark are separate files paired with `<picture>` rather than one file with a media
query, because that is what GitHub renders reliably.

## Raster output

`social-*.png` (2560×1280, 2× of GitHub's 1280×640 slot) is produced from the SVG with a
headless browser, which is the only rasteriser that respects the layout exactly:

```bash
chrome --headless --force-device-scale-factor=2 --window-size=1280,640 \
       --screenshot=docs/assets/social-light.png file://$PWD/wrap.html
```

Upload it under **Settings → General → Social preview**. GitHub does not accept SVG there.
