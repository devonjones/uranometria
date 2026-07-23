"""Command-line interface: uranometria chart / uranometria annotate."""

import os
import sys

import click
import yaml

from . import __version__
from .core import SkymapError, generate


@click.group()
@click.version_option(__version__, prog_name="uranometria")
def main():
    """Star charts and annotated astrophotos for the objects you've imaged."""


@main.command()
@click.argument("config", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False),
    help="output HTML path (default: <config>.html)",
)
@click.option("--offline", is_flag=True, help="never call the online Sesame resolver")
@click.option(
    "--mirror",
    is_flag=True,
    help="mirrored (celestial-globe) orientation; same as 'mirror: true' in the config",
)
def chart(config, output, offline, mirror):
    """Generate an HTML sky chart from a YAML object list."""
    out = output or os.path.splitext(config)[0] + ".html"
    try:
        with open(config) as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            raise SkymapError(f"{config} is not a mapping")
        if mirror:
            cfg["mirror"] = True
        warnings = generate(cfg, out, allow_online=not offline)
    except (SkymapError, FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e)) from None
    for w in warnings:
        click.echo(f"note: {w}", err=True)
    click.echo(f"wrote {out} ({os.path.getsize(out) // 1024} KB)")


@main.command()
@click.argument("image", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False),
    help="output JSON path (default: <image>.annotations.json)",
)
@click.option(
    "--mag-limit", default=12.5, show_default=True, help="faintest field stars to include"
)
@click.option("--max-stars", default=15, show_default=True, help="most field stars to include")
@click.option("--offline", is_flag=True, help="skip SIMBAD/VizieR star queries (DSOs only)")
@click.option("--astap", help="path to the astap_cli binary (or set ASTAP_CLI)")
@click.option("--astap-db", help="path to the ASTAP star database directory (or set ASTAP_DB)")
@click.option("--ra", type=float, help="pointing hint: RA in hours")
@click.option("--dec", type=float, help="pointing hint: declination in degrees")
@click.option(
    "--radius", default=30.0, show_default=True, help="search radius around the hint, degrees"
)
@click.option(
    "--png",
    "png_out",
    is_flag=False,
    flag_value="",
    default=None,
    help="also render the annotated PNG (optionally to PATH; default <image>_annotated.png)",
)
@click.option("--title", help="title for the rendered PNG (default: nearest DSO to center)")
def annotate(
    image, output, mag_limit, max_stars, offline, astap, astap_db, ra, dec, radius, png_out, title
):
    """Plate-solve IMAGE and write its annotation model (JSON).

    Solve the star-rich stack, not a starless render. Requires the [annotate]
    extra (astropy + astroquery) and the ASTAP command-line solver.
    """
    from .annotate import AstapError, build_model, write_model

    out = output or os.fspath(image) + ".annotations.json"
    solve_kwargs = {"astap": astap, "db_dir": astap_db, "radius": radius}
    if ra is not None and dec is not None:
        solve_kwargs.update(ra_hours=ra, dec=dec)
    try:
        model = build_model(
            image,
            mag_limit=mag_limit,
            max_stars=max_stars,
            allow_online=not offline,
            solve_kwargs=solve_kwargs,
        )
    except (AstapError, ValueError, OSError) as e:
        raise click.ClickException(str(e)) from None
    except ImportError as err:
        # the annotate subpackage imports lazily, so a missing dependency
        # surfaces here at first use rather than at `from .annotate import`
        raise click.ClickException(
            f"the annotate feature needs the [annotate] extra ({err}). "
            'Install with: uv tool install "uranometria[annotate] @ git+https://github.com/devonjones/uranometria"'
        ) from None
    write_model(model, out)
    for w in model["warnings"]:
        click.echo(f"note: {w}", err=True)
    s = model["solved"]
    dsos = sum(1 for o in model["objects"] if o["kind"] == "dso")
    stars = sum(1 for o in model["objects"] if o["kind"] == "star")
    click.echo(
        f"solved: center {s['center_ra']:.4f}° {s['center_dec']:+.4f}° · "
        f"{s['scale_arcsec_px']}\"/px · FOV {s['fov_deg'][0]}°×{s['fov_deg'][1]}°"
    )
    click.echo(f"wrote {out} ({dsos} DSOs, {stars} stars)")
    if png_out is not None:
        from .annotate.render_png import render_png

        png_path = png_out or os.path.splitext(os.fspath(image))[0] + "_annotated.png"
        try:
            render_png(model, image, png_path, title=title)
        except (ValueError, OSError) as e:
            raise click.ClickException(str(e)) from None
        click.echo(f"wrote {png_path}")


@main.command("render")
@click.argument("model", type=click.Path(exists=True, dir_okay=False))
@click.argument("image", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False),
    help="output PNG path (default: <image>_annotated.png)",
)
@click.option("--title", help="title bar text (default: nearest DSO to center)")
def render(model, image, output, title):
    """Render an annotated PNG from an existing annotation MODEL and its IMAGE."""
    try:
        from .annotate.render_png import render_png
    except ImportError as err:
        raise click.ClickException(f"rendering needs the [annotate] extra ({err}).") from None
    out = output or os.path.splitext(os.fspath(image))[0] + "_annotated.png"
    try:
        render_png(model, image, out, title=title)
    except (ValueError, OSError) as e:
        raise click.ClickException(str(e)) from None
    except ImportError as err:
        raise click.ClickException(f"rendering needs the [annotate] extra ({err}).") from None
    click.echo(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
