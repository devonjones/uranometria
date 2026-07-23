# The annotation model

`uranometria annotate` writes one JSON file per image. That file is the
contract between the solve/cross-match pipeline and every renderer, and it is
designed to be edited by hand: generate it once, tune it, re-render as many
times as you like.

## The generate / edit / re-render workflow

```sh
uranometria annotate stack.fit -o m51.json      # solve + cross-match (once)
$EDITOR m51.json                                # tune the annotations
uranometria render m51.json stack.fit -o out.png
```

`render` consumes the JSON as-is: no re-solving, no network. Your edits are
authoritative. Useful edits:

- **Remove an object**: delete its entry from `objects`.
- **Rename or relabel**: `designation`, `name`, and `aliases` are plain
  strings; the image shows `designation`, the legend shows everything.
- **Recolor by class**: the renderer picks colors from the `type` string, so
  changing the type changes the color family.
- **Fix data**: `dist_ly`, `mag`, field-star `key` numbers.
- **Nudge a marker**: edit `x` / `y` (pixels).

Two cautions:

- **A hand-added object needs pixel `x`/`y`.** The renderer does not
  re-project ra/dec, so a new entry must carry its pixel position.
- **Leave the geometry fields alone** (`image_size`, `pixel_frame`,
  `solved.cd`) unless you know exactly why you are changing them. They bind
  the model to the image; the size check exists to catch wrong pairings.

## Schema (version 1)

```json
{
  "schema": 1,
  "image": "M_51_1411x20sec_drizz.fit",
  "image_size": [3872, 2192],
  "solved": {
    "pixel_frame": "fits0",
    "cd": [[-0.00032993, 0.0000102], [0.00001023, 0.00032992]],
    "center_ra": 202.5166,
    "center_dec": 47.2064,
    "scale_arcsec_px": 1.188,
    "fov_deg": [1.278, 0.723],
    "rotation_deg": -178.23,
    "solver": "ASTAP"
  },
  "generated": "2026-07-23T22:45:10+00:00",
  "objects": [ ... ],
  "warnings": [ ... ]
}
```

| Field | Meaning |
|-------|---------|
| `schema` | model format version; currently 1 |
| `image` | basename of the solved image |
| `image_size` | `[width, height]` in pixels; renderers verify this against the image they are given |
| `solved.pixel_frame` | which pixel frame `x`/`y` (and `cd`) are in; see below |
| `solved.cd` | the 2x2 WCS CD matrix, pixel steps to tangent-plane degrees; drives the compass |
| `solved.center_ra`, `center_dec` | solved field center, J2000 degrees |
| `solved.scale_arcsec_px` | plate scale |
| `solved.fov_deg` | `[width, height]` field of view in degrees |
| `solved.rotation_deg` | solver-reported field rotation |
| `solved.solver` | which solver produced the WCS |
| `generated` | ISO timestamp of the model build |
| `warnings` | human-readable notes from the build (offline mode, failed queries) |

### Pixel frames

`x` and `y` are 0-indexed pixels; x grows rightward.

- `"fits0"` (FITS sources): y follows FITS row order. Drawing onto the array
  as astropy loads it needs no conversion.
- `"raster0"` (JPEG/PNG sources): y is top-down in the raster's own frame.
  Drawing onto the file as PIL loads it needs no conversion.

ASTAP always solves in FITS row order internally; for raster sources the
model builder converts y and the CD matrix's second column at build time, so
the stored coordinates are always directly drawable on their own image. The
bundled renderer also reconciles cross-kind pairings (a `fits0` model onto a
same-geometry JPEG export) by flipping y automatically.

### Object entries

Deep-sky object:

```json
{
  "kind": "dso",
  "designation": "M51",
  "aliases": ["NGC 5194"],
  "name": "Whirlpool Galaxy",
  "type": "Galaxy",
  "constellation": "Canes Venatici",
  "ra": 202.4696, "dec": 47.1952,
  "x": 1088.4, "y": 1063.7,
  "dist_ly": 22000000,
  "links": {
    "simbad": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=M51",
    "wikipedia": "https://en.wikipedia.org/wiki/Messier_51"
  }
}
```

`dist_ly` is light-years: Hubble-flow from the catalog redshift for galaxies
(approximate, shown with a tilde), a SIMBAD measured distance otherwise, or
null. `wikipedia` appears for Messier objects and objects with a common name.

Named bright star:

```json
{
  "kind": "star",
  "named": true,
  "designation": "HD 117815",
  "type": "Star (A5)",
  "ra": 202.859, "dec": 47.269,
  "x": 205.1, "y": 1112.8,
  "mag": 7.08, "band": "V",
  "dist_ly": 365,
  "links": { "simbad": "..." }
}
```

Field star:

```json
{
  "kind": "star",
  "named": false,
  "key": 6,
  "designation": "TYC 3463-582-1",
  "ra": 202.71, "dec": 47.11,
  "x": 1500.2, "y": 830.0,
  "mag": 10.9, "band": "G",
  "dist_ly": 3196,
  "links": { "simbad": "..." }
}
```

`key` is the number drawn beside the circle on the image and shown in the
legend table. `band` says which magnitude system `mag` is in (V for SIMBAD
named stars, G for Gaia field stars). All distances are light-years.
