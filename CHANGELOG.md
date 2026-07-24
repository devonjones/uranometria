# Changelog

All dates 2026. Versions bump whenever behavior visible in the output
changes, so they move fast.

## 0.10.2 (July 24)

- DSO distance lookups go to SIMBAD as one batched request for the whole
  field instead of one query per object, cutting several round-trips per
  annotation run. The per-object loop remains as a fallback if the batch
  request fails.

## 0.10.1 (July 24)

- High-proper-motion stars get their Tycho-2 designations again. Gaia DR3
  positions are epoch J2016 while Tycho-2 observed positions sit near
  J1991.25, so fast movers (Groombridge 1830 travels about 171 arcseconds
  in that gap) always missed the 2 arcsecond match and fell back to the
  raw Gaia id. Gaia proper motions now propagate the match position to
  each Tycho row's own observation epochs (they vary star by star, which
  is why even a fixed catalog-mean epoch left fast movers several
  arcseconds out).

## 0.10.0 (July 24)

- Photo thumbnails on the chart, opt-in with `thumbnails: true`. Hovering
  a marker or a legend card floats a small preview by the cursor, and
  zooming a disc past 4x pins the thumb beside the marker. Thumbs are
  built with Pillow at generation time and embedded as data URIs, so the
  page stays self-contained; remote images are never fetched and simply
  go without.

## 0.9.1 (July 24)

- Dragging to pan no longer selects the chart text: the pan/zoom surfaces
  suppress text selection and clear any live selection when a pan starts.
- Wheeling past the zoom limit no longer drifts the view toward the
  cursor. The scale is clamped before the origin moves, so at either
  clamp the wheel is a clean no-op and the page never scrolls.

## 0.9.0 (July 23)

- Sharpless entries now merge into their NGC/IC counterpart when both
  catalogs list the same nebula (IC 405 and Sh2-229 were showing up as two
  objects because the catalogs disagree on the center by 6.8 arcminutes).
  Matching is one-to-one by proximity within 12 arcminutes; only plain
  nebula, emission nebula, and H II region entries can host, so dark and
  planetary nebulae never absorb a neighbor and cluster-plus-nebula
  complexes like NGC 7380 / Sh2-142 keep both labels.
- SIMBAD distances are retried under alias designations when the primary
  name returns nothing, so a merged object keeps the distance that was
  filed under its other name.
- The annotated PNG prints a MIRRORED tag under the compass when the
  solved CD matrix shows the image is a mirror of the sky. Capture
  pipelines flip frames; the tag makes an honestly reversed compass
  readable as fact instead of looking like a bug.

## 0.8.1 (July 23)

- The legend card's ANNOTATED tag opens the lightbox in annotation mode
  when the model is embedded in the page, instead of linking out to the
  standalone HTML file. The external link is only emitted for objects
  that have an annotated page but no embedded model.

## 0.8.0 (July 23)

- One shared annotation viewer for the chart lightbox and the standalone
  annotated page: overlay, card list, search, hover spotlight, and
  viewport filtering are the same code in both.
- The lightbox LABELS button became ANNOTATIONS and hides the overlay and
  the object panel together; an EXPAND button grows the viewer to fill
  the window; the panel gained the standalone page's search box.
- The OPEN INTERACTIVE button is gone; with the model embedded, the
  external page adds nothing.
- Pan and zoom map through the true rendered scale, so zoom anchors under
  the cursor even when the SVG is letterboxed (EXPAND mode, standalone
  page at any window shape).
- Hand-edited and third-party model files are treated as untrusted:
  sizes and scales are coerced and validated, link URLs must be http(s),
  JSON payloads escape every angle bracket, and non-finite numbers
  degrade to the documented warning instead of killing the page script.

## 0.7.0 (July 23)

- The sky chart embeds annotation models directly in the page (an
  `annotations:` key in the config, or a `<image>.annotations.json`
  sidecar found automatically). The lightbox shows the full object panel
  with aliases, magnitudes, distances, and SIMBAD/Wikipedia links,
  filtered to the region in view as you zoom, with no dependency on the
  standalone annotated HTML staying where it was.

## 0.6.0 (July 23)

- Standalone interactive HTML page for a single annotated image: the
  photograph embedded as a data URI, pan and zoom with counter-scaled
  markers, and a searchable sidebar linking each object to SIMBAD and
  Wikipedia.
- The sky-map lightbox draws the annotation overlay on the photo with a
  labels toggle, and zooms and pans like the chart discs; only the
  backdrop or Escape dismisses it.
- Overlay label size scales with the image and is configurable
  (`--label-scale`, `annotation_label_scale:`).
- Consistent distances in light-years everywhere, with cluster/nebula
  pair distances harmonized and a deeper display stretch for FITS.

## 0.5.0 (July 23)

- Annotated PNG renderer: markers and leader labels colored by object
  class, numbered circles for field stars keyed to a legend panel,
  N/E compass from the solved CD matrix, and a 10-arcminute scale bar.
- Raster solves (JPEG/PNG) handle ASTAP's FITS-order coordinates
  correctly; the model records its pixel frame so renderers flip only
  when compositing across kinds.

## 0.4.0 (July 23)

- Annotation pipeline: offline plate solving through the ASTAP CLI,
  cross-matching against the bundled catalogs plus Gaia DR3, Tycho-2, and
  SIMBAD (all via CDS services, gated behind `--offline`), written to a
  documented JSON model built for the generate, edit, re-render loop.
- The CLI became a click command group: `uranometria chart | annotate |
  render`.

## 0.3.1 (July 23)

- Fixes from a full-codebase review: M102 resolves through its addendum
  entry, malformed coordinates in the config warn and skip instead of
  crashing, and hostile strings in config values arrive inert in the
  generated markup.

## 0.3.0 (July 23)

- Charts default to true sky view: RA runs clockwise on the northern
  disc, matching what you see looking up. The 0.2.0 orientation was the
  mirror image. A `mirror:` option keeps the celestial-globe view
  available.

## 0.2.0 (July 23)

- Initial release: star-atlas style polar charts of your imaged deep-sky
  objects from a YAML config. Messier, NGC/IC, Caldwell, and Sharpless
  designations resolve against bundled catalogs (CDS Sesame as an online
  fallback); southern hemisphere appears automatically when needed, with
  a toggle when both are present. Zoom, pan, search, and viewport
  filtering; per-object photos in a lightbox; colors, manual coordinates,
  and self-contained single-file output.
