#!/usr/bin/env bash
# Assemble the GitHub Pages site: live samples plus generated API docs.
# Used by .github/workflows/pages.yml and for local verification:
#   scripts/build-pages-site.sh out/site
set -euo pipefail
site="${1:?usage: build-pages-site.sh OUTPUT_DIR}"
rm -rf "$site"
mkdir -p "$site"
cp -r examples "$site/examples"
touch "$site/.nojekyll"
uv run pdoc \
  uranometria \
  uranometria.core \
  uranometria.catalog \
  uranometria.chart \
  uranometria.page \
  uranometria.webui \
  uranometria.cli \
  uranometria.annotate \
  uranometria.annotate.model \
  uranometria.annotate.field \
  uranometria.annotate.solver \
  uranometria.annotate.render_png \
  uranometria.annotate.render_html \
  -o "$site/api"
cat > "$site/index.html" <<'HTML'
<!doctype html>
<title>uranometria</title>
<meta charset="utf-8">
<style>body{font-family:monospace;background:#070B1B;color:#C7CEE6;padding:40px}
a{color:#E5B958}</style>
<h1>uranometria</h1>
<ul>
<li><a href="examples/skymap.html">live sample chart</a></li>
<li><a href="examples/annotated/M51_annotated.html">live annotated image</a></li>
<li><a href="api/">API documentation</a></li>
<li><a href="https://github.com/devonjones/uranometria">source on GitHub</a></li>
</ul>
HTML
echo "site assembled at $site"
