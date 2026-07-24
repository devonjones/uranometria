# Annotating images

`uranometria annotate` plate-solves a stacked astrophoto, works out what is
in the frame, and writes an [annotation model](annotation-model.md) as JSON.
Add `--png` to also render the annotated image: callouts for deep-sky
objects, named bright stars with magnitudes and distances, numbered field
stars keyed to a legend table, a title bar with the solve, an N/E compass,
and a scale bar.

```sh
uranometria annotate stack.fit --png
uranometria annotate stack.fit --ra 13.5 --dec 47.2      # pointing hint, faster solve
uranometria annotate seestar.jpg -o wizard.json --png wizard.png
uranometria render wizard.json seestar.jpg -o wizard.png  # re-render, no re-solve
```

## Prerequisites

1. **The `annotate` extra** (astropy, astroquery, pillow, matplotlib):

   ```sh
   pip install "uranometria[annotate] @ git+https://github.com/devonjones/uranometria"
   ```

2. **The ASTAP command-line solver** with a local star database, from
   [hnsky.org/astap.htm](https://www.hnsky.org/astap.htm). The D20 database
   (~400 MB) solves Seestar-scale fields (around 1°) comfortably; D50 covers
   smaller fields. Point uranometria at them with `--astap` / `--astap-db`,
   or set the `ASTAP_CLI` and `ASTAP_DB` environment variables once:

   ```sh
   export ASTAP_CLI=~/astap/astap_cli
   export ASTAP_DB=~/astap
   ```

Solving is fully offline through ASTAP's bundled database. The catalog
cross-match uses the bundled OpenNGC/Sharpless data for deep-sky objects
(offline) and CDS services for stars and distances (online, see below).

## What to solve

**Solve the star-rich stack, not a starless or heavily processed render.**
The solver matches star patterns; a starless image cannot solve, and heavy
processing (strong star reduction, aggressive sharpening) can leave too few
clean stars for a match. Good inputs:

- Siril stacks from `stacks/` (FITS)
- device stacks (Seestar JPEG stacks solve fine)
- lightly processed renders that keep their stars

FITS, JPEG, PNG, and TIFF all work as inputs. The output model records which
kind it was solved from (`pixel_frame`), and the renderer reconciles frames
automatically, so you can solve a FITS stack and later composite the labels
onto a same-geometry export if you have one. The image dimensions must match
the model exactly; the renderer refuses mismatched pairs.

## Command reference

### `uranometria annotate IMAGE`

| Option | Meaning |
|--------|---------|
| `-o, --output FILE` | model JSON path (default `<image>.annotations.json`) |
| `--mag-limit FLOAT` | faintest field stars to include (default 12.5, Gaia G) |
| `--max-stars N` | most field stars to label (default 15, brightest in frame) |
| `--offline` | skip SIMBAD/VizieR: deep-sky objects only, no field stars or distances |
| `--astap PATH` | astap_cli binary (or env `ASTAP_CLI`) |
| `--astap-db PATH` | star database directory (or env `ASTAP_DB`) |
| `--ra HOURS --dec DEG` | pointing hint; makes the solve near-instant |
| `--radius DEG` | search radius around the hint (default 30) |
| `--png [PATH]` | also render the annotated PNG (default `<image>_annotated.png`) |
| `--title TEXT` | title bar text (default: the DSO nearest the frame center) |
| `--label-scale X` | multiplier for overlay label size in the HTML page (default 1.0) |

### `uranometria render MODEL IMAGE`

Renders an annotated PNG from an existing model, with no solving and no
network. `-o/--output` names the PNG (default `<image>_annotated.png`),
`--title` overrides the title bar. This is the second half of the
generate / edit / re-render workflow described in
[annotation-model.md](annotation-model.md).

## The interactive HTML page

`--html` (on `annotate`) or `render --html` produces one self-contained HTML
file: the photograph embedded as a data URI, the overlay drawn in SVG with
counter-scaled markers, wheel zoom and drag pan, an ANNOTATIONS toggle
(hides the overlay and the object panel together), and a
searchable sidebar where every object links to SIMBAD (and Wikipedia when an
article is likely). FITS sources are rendered through the same display
stretch as the PNG before embedding.

## The sky-map lightbox overlay

If a chart object's photo has an annotation model sitting next to it as
`<image>.annotations.json` (or named explicitly with an `annotations:` key in
the chart config), the sky map's lightbox draws the overlay on the photo with
an ANNOTATIONS toggle (on by default, remembered per session; hides the
overlay and the panel together) and shows a side panel listing every
identified object: designations with aliases, common name, type, magnitude,
distance, and SIMBAD/Wikipedia links, with a search box. Zooming the photo
filters the panel to the objects in view, hovering a card spotlights that
object on the image, and an EXPAND button grows the viewer to fill the
window. The lightbox and the standalone page are built by the same shared
code, so they behave identically. The model is embedded in the chart page
when the chart is built, so the annotation viewer travels with the page and
does not depend on the standalone annotated HTML existing or staying put.
The overlay only engages when the model's `image_size` matches
the displayed photo, so a model built from a different crop is ignored rather
than misdrawn. The lightbox itself zooms and pans like the chart discs;
clicking the photo never closes it, only the backdrop or Esc does.

To wire the pipelines together by hand: solve once, save the model with the
sidecar name, and rebuild the chart.

```bash
uranometria annotate stack.fit -o heroes/M51.jpg.annotations.json
uranometria chart skymap.yaml -o skymap.html
```

See [chart configuration](chart-config.md#annotations) for the `annotations:`
key when the model lives elsewhere.

## What gets identified

- **Deep-sky objects**: everything from the bundled OpenNGC + Sharpless
  catalogs that lands in the frame, with aliases collapsed (M51 and NGC 5194
  become one entry listing both) and distances where available: Hubble-flow
  estimates from catalog redshifts for galaxies, SIMBAD measured distances
  for nebulae and clusters.
- **Named bright stars**: SIMBAD stars brighter than V≈8.5 in the field, with
  HD/proper designations, spectral types, and parallax distances.
- **Field stars**: Gaia DR3 magnitudes and parallax distances via VizieR,
  with Tycho-2 designations where a match exists, brightest first up to
  `--max-stars`.

All star and distance queries go through CDS services (VizieR, SIMBAD); the
Gaia archive itself is never contacted. Failures degrade to warnings, never
crashes. With `--offline` you still get the deep-sky objects, since those
come from bundled data.

## The rendered PNG

Colors by object class: galaxies blue, emission nebulae pink, planetaries
teal, clusters orange, dark nebulae violet, named stars yellow, field stars
green. Objects typed "cluster + nebula" (NGC 7380, M42) read as clusters
here, because the Sharpless nebula appears as its own labeled entry alongside.

Leader lines avoid crossing neighboring objects where the geometry allows,
labels stay inside the frame, and the compass is computed from the solved CD
matrix, so it stays honest for mirrored images. Distances display in
light-years throughout (Mly for galaxies).
