# Sky charts

`uranometria chart` turns a YAML list of objects into a single self-contained
HTML page: a polar star chart with your imaged objects marked on it, in the
style of a classical star atlas.

```sh
uranometria chart skymap.yaml                 # writes skymap.html next to the config
uranometria chart skymap.yaml -o map.html
uranometria chart skymap.yaml --offline       # never call the online resolver
uranometria chart skymap.yaml --mirror        # mirrored (celestial-globe) view
```

The config format is documented in [chart-config.md](chart-config.md).

## What the chart shows

Each hemisphere is an azimuthal equidistant disc centered on the celestial
pole, extending 35° past the equator, with:

- stars to the configured magnitude limit (default 5.0), sized by brightness
  and tinted by color index
- constellation stick figures and Latin names
- declination circles, right-ascension spokes with hour labels, the celestial
  equator, and the ecliptic as a dashed curve
- a gold reticle marker for every object in your config, labeled with its
  designation

Charts default to **sky view**: the sky as it actually appears from Earth,
which means right ascension runs clockwise around a northern polar disc and
counterclockwise around a southern one. `--mirror` (or `mirror: true` in the
config) flips to the celestial-globe orientation, which also matches the view
through a telescope star diagonal.

If any object sits south of declination −35°, the page gets both discs and a
NORTHERN / SOUTHERN toggle above the chart. When both discs exist, objects
land on the disc of their own hemisphere; the sidebar follows whichever disc
is showing.

## Using the page

The generated page is interactive:

- **Zoom and pan**: mouse wheel zooms about the cursor (up to 8x), drag pans,
  double-click resets. Markers and labels keep their screen size as you zoom,
  so dense regions untangle instead of scaling up.
- **Sidebar**: every object appears in the observing record on the right,
  with its own scrollbar so the list scrolls independently of the chart.
  Hovering an entry spotlights its marker.
- **Search**: the box above the list filters by designation, common name,
  type, or constellation, and dims everything else on the chart.
- **Zoom filtering**: when you zoom in, the sidebar narrows to the objects in
  the visible region (the count shows "N OF M OBJECTS · IN VIEW").
- **Thumbnails** (`thumbnails: true` in the config): hovering a marker
  floats a small preview of the object's photo by the cursor, hovering a
  legend card pins the preview at the object's marker on the chart, and
  zooming past 4x pins it beside the marker for every photographed object
  in view. Clicking the floating preview, the marker, or its pinned thumb
  opens the photo in the lightbox.
- **Links**: every legend card links to SIMBAD, plus Wikipedia when the
  article name is a safe bet, plus any article links from the config's
  `links:` key. Zooming filters the sidebar, so the visible objects'
  links follow the view.
- **Photos**: objects with an `image:` in the config get a "PHOTO" tag; click
  the marker or the card to open the photo in a lightbox. The photo zooms and
  pans like the chart (wheel, drag, double-click to reset); clicking the
  photo never dismisses it, only the backdrop or Esc does. If the photo has
  an annotation model (an `annotations:` key in the config, or a sidecar
  named `<image>.annotations.json` beside the photo), the lightbox becomes a
  full annotation viewer, the same one the standalone annotated page uses:
  the identified objects drawn over the image, and a searchable side panel
  listing every object with its aliases, type, magnitude, distance, and
  SIMBAD/Wikipedia links. The panel filters to the objects in view as you
  zoom, hovering a card spotlights that object on the image, an ANNOTATIONS
  button toggles the overlay and panel together, and EXPAND grows the viewer
  to fill the window. All of it is embedded in the chart page itself, so it
  keeps working if the standalone annotated HTML moves or was never
  generated. The legend card's ANNOTATED tag opens the lightbox with
  annotations switched on, whatever the toggle's remembered state.

## Self-contained output

The page is one HTML file with no external dependencies: fonts are embedded
as data URIs, the star and constellation data is inlined, and the JavaScript
is plain inline code. It renders identically from a local file, a USB stick,
or a static host, with no network access. The one exception is object photos,
which are referenced by path or URL, not embedded; keep them alongside the
page (paths resolve relative to the output file).

## Regenerating as your library grows

Add the new object to your YAML and re-run the command. Designation lookups
for Messier, NGC, IC, Sharpless, Caldwell, and friends are resolved from
catalogs bundled inside the package, so regeneration is offline and
deterministic; only unknown designations fall back to the CDS Sesame resolver
(disable with `--offline`).
