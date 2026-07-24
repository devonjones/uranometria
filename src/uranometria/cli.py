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
@click.option(
    "--html",
    "html_out",
    is_flag=False,
    flag_value="",
    default=None,
    help="also render the interactive HTML page (optionally to PATH; default <image>_annotated.html)",
)
@click.option(
    "--label-scale",
    default=1.0,
    show_default=True,
    help="multiplier for overlay label size in the HTML page",
)
@click.option("--title", help="title for rendered outputs (default: nearest DSO to center)")
def annotate(
    image,
    output,
    mag_limit,
    max_stars,
    offline,
    astap,
    astap_db,
    ra,
    dec,
    radius,
    png_out,
    html_out,
    label_scale,
    title,
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
        except ImportError as err:
            raise click.ClickException(f"rendering needs the [annotate] extra ({err}).") from None
        click.echo(f"wrote {png_path}")
    if html_out is not None:
        from .annotate.render_html import render_html

        html_path = html_out or os.path.splitext(os.fspath(image))[0] + "_annotated.html"
        try:
            render_html(model, image, html_path, title=title, label_scale=label_scale)
        except (ValueError, OSError) as e:
            raise click.ClickException(str(e)) from None
        except ImportError as err:
            raise click.ClickException(f"rendering needs the [annotate] extra ({err}).") from None
        click.echo(f"wrote {html_path}")


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
@click.option(
    "--html", "as_html", is_flag=True, help="render the interactive HTML page instead of a PNG"
)
@click.option(
    "--label-scale",
    default=1.0,
    show_default=True,
    help="multiplier for overlay label size (HTML page only)",
)
def render(model, image, output, title, as_html, label_scale):
    """Render an annotated PNG (or, with --html, the interactive page) from an
    existing annotation MODEL and its IMAGE."""
    ext = ".html" if as_html else ".png"
    out = output or os.path.splitext(os.fspath(image))[0] + "_annotated" + ext
    try:
        if as_html:
            from .annotate.render_html import render_html

            render_html(model, image, out, title=title, label_scale=label_scale)
        else:
            from .annotate.render_png import render_png

            render_png(model, image, out, title=title)
    except (ValueError, OSError) as e:
        raise click.ClickException(str(e)) from None
    except ImportError as err:
        raise click.ClickException(f"rendering needs the [annotate] extra ({err}).") from None
    click.echo(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
