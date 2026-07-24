# Chart config reference

A chart config is a YAML mapping. Only `objects` is required.

```yaml
title: The Northern Sky        # page title (default: THE NORTHERN/SOUTHERN/NIGHT SKY)
subtitle: My observing record  # line under the title (default: "N DEEP-SKY OBJECTS · EPOCH J2000")
mag_limit: 5.0                 # faintest stars drawn on the chart (default 5.0)
show_ecliptic: true            # dashed ecliptic curve (default true)
mirror: false                  # true = mirrored (celestial-globe) orientation
objects:
  - ...                        # see below
```

`mag_limit` must be a number; anything else (including NaN) raises
`SkymapError`. The `--mirror` CLI flag is equivalent to `mirror: true`.

## Object entries

Three forms, freely mixed:

### 1. Bare designation

```yaml
objects:
  - M31
  - NGC 7380
  - Sh2-142
  - Pleiades
```

Strings (and bare numbers, which are treated as strings) are looked up in the
bundled catalogs, then in the CDS Sesame online resolver if unknown.

### 2. Lookup with overrides

```yaml
  - id: Sh2-142
    label: NGC 7380            # display designation on the chart and legend
    name: Wizard Nebula        # common name shown in the legend
    type: Emission nebula      # legend type text
    constellation: Cepheus     # legend constellation
    image: Images/wizard.jpg   # click-to-view photo (see below)
    color: "#D98A7E"           # marker/label/legend accent, any CSS color
```

`id` is resolved like a bare designation; every other field overrides what
the catalog returned. All override fields are optional.

### 3. Fully manual entry

```yaml
  - label: PN G75.5+1.7
    name: Soap Bubble Nebula
    type: Planetary nebula
    constellation: Cygnus
    ra: "20h15m22s"
    dec: "+38 21 18"
    image: images/soap.jpg
    color: "#E06C75"
```

When both `ra` and `dec` are present, no lookup happens at all. Coordinate
formats accepted:

- decimal degrees: `303.84` (number or string)
- sexagesimal with unit marks: `20h15m22s`, `-05d23m28s`, `+41°16′09″`
- colon separated: `20:15:22`, `-38:21:18`
- space separated: `"20 15 22"` (RA values ≤ 24 with multiple parts are
  treated as hours; add an explicit `d` or `°` to force degrees)

RA is normalized into [0°, 360°). A dec outside ±90° is skipped with a
warning. A malformed coordinate skips that object with a warning; it never
aborts the chart.

## Designations resolved offline

The bundled catalogs cover, with no network at all:

- **Messier** M1 to M110, including the oddballs (M40, M45, M102)
- **NGC and IC**, the full OpenNGC database, including duplicate-entry
  resolution (looking up IC 11 lands on NGC 281's position)
- **Sharpless** Sh2-1 through Sh2-313 (spellings like `sh 2-142` and `S142`
  work)
- **Caldwell** C1 through C109 (`C9`, `Caldwell 14`)
- **Barnard 33** and the Melotte clusters OpenNGC carries (`Mel 25` resolves
  to the Hyades)
- **Common names** OpenNGC knows: "Pleiades", "Horsehead Nebula",
  "Whirlpool Galaxy", and so on

Anything else (vdB, Collinder, Abell, Arp, LBN, Gaia ids, star names) goes to
the CDS Sesame resolver, which needs the network. `--offline` (CLI) or
`allow_online=False` (library) turns that off; unresolvable objects are
skipped with a warning.

## Images

`image:` makes the object clickable on the chart and in the sidebar. It can
be:

- an `http(s)` URL, passed through untouched
- an absolute path, emitted as a `file://` link
- a relative path, resolved **relative to the output HTML file** and checked
  at build time; a missing file prints a note and renders that object without
  its photo

Paths with spaces are fine (they are URL-encoded).

## Annotations

`annotations:` names an [annotation model](annotation-model.md) for the
object's photo (path resolved like `image:`). Without it, a sidecar named
`<image>.annotations.json` next to the photo is picked up automatically. When
present and matching the photo's dimensions, the lightbox draws the overlay
with a LABELS toggle and shows a side panel listing every identified object
with aliases, magnitude, distance, and SIMBAD/Wikipedia links, filtered to
the region in view as you zoom. The model is embedded in the chart page at
build time, so the viewer works wherever the page goes. An unreadable
sidecar is a warning, never a failure.

This is the bridge between the two pipelines. Generate the model once with
the annotate command, then point the chart at it:

```bash
uranometria annotate Images/M51/stack.fit -o Images/M51/finished/M51.jpg.annotations.json
```

```yaml
objects:
  - id: M51
    image: Images/M51/finished/M51.jpg
    annotations: Images/M51/finished/M51.jpg.annotations.json  # or omit: the
                                                # sidecar name above is found
                                                # automatically
```

The model must be built from the same pixels as the photo it annotates (same
image or an unscaled export of it); a size mismatch quietly disables the
overlay instead of drawing circles in the wrong place.

`annotation_label_scale:` (chart-level, default 1.0) multiplies the size of
overlay labels drawn in the lightbox.

`annotated:` links the object to its interactive annotated page (built with
`render --html`), shown as an ANNOTATED link on the legend card and an OPEN
INTERACTIVE button in the lightbox. Without the key, a sibling file named
`<image stem>_annotated.html` is picked up automatically. This pairs well
with keeping the pretty hero as `image:` while the interactive page carries
the labeled version.

## Colors

`color:` accepts any CSS color and tints that object's marker, chart label,
and sidebar card. Use it to encode whatever you like: object class, stack
depth, capture season. Without it, everything is the default brass gold.

## Warnings and errors

Per-object problems (unresolvable designation, bad coordinates, missing
image) come back as warning strings on stderr and the object is skipped or
rendered without its photo. `SkymapError` is raised only when no chart can be
produced at all: an empty `objects` list, nothing resolvable, or an invalid
chart-level value like a non-numeric `mag_limit`.

## Library use

The library takes the same structure as a plain dict, no YAML involved:

```python
import uranometria

warnings = uranometria.generate({"objects": ["M31", "M42"]}, "map.html")
html, warnings = uranometria.render({"objects": ["M31"]}, image_base="out")
```

Pass `allow_online=False` to stay offline. `generate` resolves relative image
paths against the output file's directory; `render` uses `image_base`.
