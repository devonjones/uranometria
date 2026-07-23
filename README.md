# uranometria

Star-atlas style HTML sky charts of the deep-sky objects you've photographed.

Each chart draws the constellations, a coordinate grid, and a marker for
everything you've imaged. Objects can carry a photo (click the marker or the
legend entry to see it), and markers can be colored however you like, say by
object type or by how deep the stack is. The page itself is interactive:
scroll to zoom, drag to pan, double-click to reset. A sidebar lists every
object with a search box, and both search and zoom narrow the list to what
you're actually looking at. Works fine with five objects or a hundred and
fifty.

The name comes from Johann Bayer's
[*Uranometria*](https://en.wikipedia.org/wiki/Uranometria) (1603), the first
atlas to chart the entire celestial sphere and the source of the Greek-letter
star names we still use. Bayer engraved every star anyone had ever measured.
You just have to photograph yours.

![Example chart](examples/skymap.png)

There's a **[live sample here](https://devonjones.github.io/uranometria/examples/skymap.html)**,
built from [`examples/skymap.yaml`](examples/skymap.yaml). Click any marker
or legend card to see the photograph behind it.

## Install

Not on PyPI yet, so install from git:

```sh
uv tool install git+https://github.com/devonjones/uranometria   # CLI on your PATH
pip install git+https://github.com/devonjones/uranometria       # or plain pip
```

As a dependency of another project:

```sh
uv add "uranometria @ git+https://github.com/devonjones/uranometria"
```

From a local checkout: `uv tool install <path-to-checkout>`.

## CLI

```sh
uranometria skymap.yaml                 # writes skymap.html next to the config
uranometria skymap.yaml -o map.html
uranometria skymap.yaml --offline       # never call the online resolver
uranometria skymap.yaml --mirror        # mirrored (celestial-globe) orientation
```

Charts default to sky view, oriented the way the sky actually looks from
Earth (RA runs clockwise around a northern polar disc). If you want the
mirrored orientation instead, which matches celestial globes and the view
through a star diagonal, pass `--mirror` or set `mirror: true` in the config.

## Config

```yaml
title: The Northern Sky        # optional
subtitle: ...                  # optional
mag_limit: 5.0                 # faintest stars drawn (default 5.0)
show_ecliptic: true
mirror: false                  # true for the mirrored orientation
objects:
  - M31                        # bare designation
  - id: Sh2-142                # catalog lookup with overrides
    label: NGC 7380
    name: Wizard Nebula
  - label: PN G75.5+1.7        # fully manual entry
    name: Soap Bubble Nebula
    type: Planetary nebula
    constellation: Cygnus
    ra: "20h15m22s"            # or decimal degrees, or "20:15:22"
    dec: "+38 21 18"
    image: images/soap.jpg     # click to view; path is resolved relative to
                               #   the output HTML and checked at build time
    color: "#E06C75"           # marker/legend accent, any CSS color
```

These designations resolve offline from bundled catalogs: Messier (including
the M40/M45/M102 oddballs), NGC and IC (OpenNGC), Sharpless (Sh2-1 through
313), Caldwell, Barnard 33, Melotte, and any common name OpenNGC knows, like
"Pleiades" or "Horsehead Nebula". Anything else (vdB, Collinder, Abell, Arp,
and so on) falls back to the CDS Sesame online resolver, or you can just
enter coordinates yourself.

If any object sits south of declination -35°, a southern-hemisphere chart is
added automatically and the page gets a toggle to switch between the two.

## Library API

YAML is only the CLI's concern. The library takes plain dicts, so a host
application can build the config straight from its own object database:

```python
import uranometria

config = {
    "title": "My Sky",
    "objects": [
        "M31",
        {"id": "Sh2-142", "label": "NGC 7380"},
        {"label": "M81", "name": "Bode's Galaxy", "type": "Galaxy",
         "constellation": "Ursa Major", "ra": 148.888, "dec": 69.065,
         "image": "heroes/m81.jpg", "color": "#7EC8A0"},
    ],
}
warnings = uranometria.generate(config, "out/map.html")   # writes the file
html, warnings = uranometria.render(config, image_base="out")  # or just the HTML
```

Pass `allow_online=False` to forbid the Sesame fallback if your host has to
stay offline. When nothing can be charted at all you get a
`uranometria.SkymapError`; smaller problems like an unresolvable id or a
missing image file come back as warning strings, and the object is skipped or
rendered without its photo.

## Integrating into a host application

A workflow manager that already knows each object's designation, coordinates,
and hero image can skip every lookup by passing fully specified entries, at
which point `generate` is offline and deterministic. A reasonable pattern is
an optional dependency that degrades gracefully:

```python
try:
    import uranometria
except ImportError:
    uranometria = None   # feature hidden / "install uranometria" hint

def publish_skymap(objects, out_path):
    cfg = {"objects": [
        {"label": o.display_id, "name": o.name, "type": o.type,
         "constellation": o.constellation, "ra": o.ra_deg, "dec": o.dec_deg,
         "image": os.path.relpath(o.hero_path, out_path.parent)}
        for o in objects if o.has_captures
    ]}
    return uranometria.generate(cfg, out_path)
```

## Data & licenses

- [OpenNGC](https://github.com/mattiaverga/OpenNGC) (CC-BY-SA-4.0): NGC, IC, Messier, and Caldwell records
- Sharpless (1959) via [VizieR VII/20](https://cdsarc.cds.unistra.fr/viz-bin/cat/VII/20): Sh2 positions
- [d3-celestial](https://github.com/ofrohn/d3-celestial) (BSD-3): stars to mag 6, constellation lines and names
- Fonts: Marcellus and IBM Plex Mono (SIL OFL), embedded as data URIs
- Online fallback: the [CDS Sesame](https://cds.unistra.fr/cgi-bin/Sesame) name resolver

Code: Apache-2.0.
