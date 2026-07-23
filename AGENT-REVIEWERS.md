# Configuration

```json
{
  "defaults_version_checked": "1.6.0",
  "disabled": [
    "concurrency-reviewer",
    "external-process-reviewer",
    "logging-reviewer",
    "resource-leak-reviewer",
    "dataclass-decorator-reviewer",
    "migration-idempotency-reviewer",
    "homelab-values-reviewer",
    "silent-failure-hunter",
    "code-simplifier",
    "comment-analyzer"
  ],
  "notes": "uranometria is a single-process, pure-Python library with no threads, no subprocesses, no databases, and no long-lived resources. The disabled defaults have no scope here. The pack below replaces them with reviewers tuned to what this project actually gets wrong: sky geometry, generated markup, the offline/online boundary, bundled catalog data, and the public config surface."
}
```

# Agents

## test-coverage-reviewer

Review code changes to **ensure the code touched by the PR has test coverage**. Every PR either adds coverage or preserves it.

**Core rule: Code touched by a PR must be covered by tests. Either the coverage already exists, or this PR adds it.**

The unit of obligation is *coverage of the touched code*, not net-new test functions for every diff. A pure rename of a well-tested function does not need a new test; a new branch in that function does.

**Rules to enforce:**

1. **Coverage required for all touched code.** For any modified or new function, verify that some test exercises it. Tests live in `tests/test_skymap.py` and run with `uv run pytest`.
2. **Generated-HTML assertions are real tests here.** Most of this library's output is one big HTML string. Asserting on markers in that string (`'id="hemitoggle"'`, `"--tx:"`, `'data-img="pic.jpg"'`) is the established pattern and counts as coverage of the rendering path that emits them. A new UI feature in `page.py` or `chart.py` needs at least one such assertion.
3. **Geometry changes need value tests, not just smoke tests.** A change to `project()`, `ra_sign()`, `parse_angle()`, `fmt_coord()`, or hemisphere assignment must be covered by a test that pins actual numbers or orientation (see `test_sky_view_orientation` for the house style). "The page still generates" is not coverage for math.
4. **Catalog lookup changes need a designation table entry.** New designation forms or parser branches in `catalog.py` get a row in the `test_catalog_lookup` parametrize table, including the weird cases (the M45/Mel 22 addendum path, Caldwell-without-NGC, Dup resolution).
5. **Warning paths are behavior.** If a change adds or alters a warning string path (unresolvable id, missing image, Sesame fallback), a test must assert the warning appears and the chart still generates.

**Do NOT flag:**

- Pure formatting or comment changes.
- Changes to `examples/` content.
- Refactors where existing tests still exercise the moved code, unless the code was uncovered before the refactor. That is the moment to add the test.

**Exceptions require a beads ticket created before merge.**

---

## celestial-math-reviewer

Review changes to **coordinate handling, projection, and sky geometry** in `chart.py`, `catalog.py`, and hemisphere logic in `page.py`/`core.py`. Sky geometry is where this project has shipped its worst bug: v0.2.0 rendered both polar discs with celestial-globe chirality, the mirror image of the real sky, and nobody caught it until a user compared the chart to the night sky.

**Ground truth for this codebase:**

- Charts are **sky views**: the celestial sphere seen from inside. On an equatorial chart that means north-up/east-left; carried to the poles it means RA runs **clockwise** on a northern polar disc and **counterclockwise** on a southern one. `mirror: true` flips both.
- All chirality flows through `ra_sign(south, mirror)`. That is the only place a horizontal sign convention may live.
- Positions are J2000. RA is stored in degrees (0–360), dec in degrees (−90 to +90). `parse_angle` accepts decimal degrees and sexagesimal strings, and decides hours-vs-degrees for RA from format cues.
- Each hemisphere disc spans pole to `DEC_EDGE` (35°) past the equator. Band objects (|dec| ≤ 35°) are assigned north when `dec >= 0` if both discs exist, and to the single disc otherwise.

**FLAG (P1) when a PR:**

- Introduces a sine/cosine sign, an angle negation, or an x-mirror anywhere outside `ra_sign()`. Every one of these is a chirality bug waiting to happen.
- Changes `project()`, `ra_sign()`, or hemisphere assignment **without touching the orientation tests**. The change may be correct; unpinned it will not stay correct.
- Mixes RA hours and RA degrees. Watch for `hms()`-style helpers, `* 15` / `/ 15` conversions appearing far from parsing, or a function whose parameter name says `ra` without a unit.
- Compares RA values across the 0h/24h wrap with plain subtraction (e.g. separation or dedup logic). Angular separation must go through proper spherical math, as `sep_deg`-style code does.

**FLAG (P2) when a PR:**

- Hard-codes `35`, `125`, `470`, or `500` instead of `DEC_EDGE`, `SCALE`, `R_MAX`, `CX`/`CY`.
- Adds coordinate-dependent features (grid lines, labels, curves like the ecliptic) computed for one hemisphere and reflected ad hoc for the other, rather than derived through `self.sign` / `self.p()`.
- Changes `visible()` or clipping without a test for an object near the ±35° edge.

**Do NOT flag:**

- SVG y-axis inversion (`CY - r*cos`); screen coordinates grow downward and that is expected.
- Label placement offsets in `place_label` candidates; those are aesthetic, not geometric.

**Review approach:**

1. Diff `chart.py` for `sin`, `cos`, unary minus, and any new use of `south`/`mirror` conditionals.
2. If geometry changed, confirm `test_sky_view_orientation` (or a new sibling) changed with it.
3. Sanity-check any new angle math at the 0h wrap and at both poles.

---

## markup-safety-reviewer

Review the **HTML/CSS/JS generation** in `page.py` and `chart.py`. The entire page is built from Python f-strings, so this project's injection surface is every config value a user controls: `title`, `subtitle`, `label`, `name`, `type`, `constellation`, `color`, `image`, and every catalog string that flows into markup.

**FLAG (P1) when a PR:**

- Interpolates any user- or catalog-sourced string into markup without `html.escape()`. Attribute contexts need `html.escape(..., quote=True)`; the existing `data-img`/`data-cap`/`--accent` handling is the reference pattern.
- Interpolates a user string into a `<script>` block or an inline event handler. Nothing user-controlled belongs in the JS section; pass data through `data-*` attributes and read it from JS.
- Emits a user-supplied path into a URL context without `urllib.parse.quote()` (see `resolve_image`; image paths contain spaces in real libraries, e.g. Seestar `Stacked_60_M 1_...jpg`).
- Breaks f-string brace escaping in the template. CSS/JS blocks inside `build_page` must use `{{` and `}}`; a stray single brace turns a style rule into a silent `KeyError` or mangled output. Any edit inside the big template f-string deserves a squint at its braces.

**FLAG (P2) when a PR:**

- Adds an `id` attribute generated from user data (collision/DOM-clobbering risk). Generated ids should stay index-based (`mk-{i}`).
- Duplicates escape logic instead of reusing the established call sites.
- Adds JS that assumes exactly one chart svg. Everything must work with one or two discs (`document.querySelectorAll('svg.sky')`, per-svg `_vb` state).

**Do NOT flag:**

- Unescaped **literal** strings authored in this repo (headings, hints, footer text).
- The `color` value flowing into a `style` attribute after `html.escape(quote=True)`. A hostile CSS value can at worst restyle the page the user themselves generated; this is a local file generator, not a hosted app.

**Review approach:**

1. Grep the diff for `f'` / `f"` strings containing `<` and for `.format(`.
2. For each interpolation, trace the value to its source; user/catalog origin requires an escape at the sink.
3. Render a config containing a hostile label (`<img src=x onerror=alert(1)>`, quotes, backslashes) and confirm it arrives inert in the output.

---

## self-contained-output-reviewer

Review changes for the **self-contained output guarantee**: a generated chart is one HTML file that renders complete with no network access, forever. People archive these, open them off USB sticks, and publish them behind strict CSPs.

**FLAG (P1) when a PR:**

- Adds an external `src`, `href`, `@import`, or `fetch()` to the generated page: CDN scripts, Google Fonts stylesheets, remote images, analytics, anything. Fonts stay base64 data URIs; JS stays inline and vanilla.
- Makes chart generation itself require network for previously-offline paths (see `network-boundary-reviewer` for the one sanctioned exception).

**FLAG (P2) when a PR:**

- Adds a JS framework, build step, or minifier for the inline script. The page's JS is a few hundred lines of vanilla DOM code on purpose; a toolchain is a bigger liability than the verbosity.
- Bloats the page meaningfully. Fonts are subset for a reason (~20 KB each); a full font family or an embedded megabyte of data needs justification in the PR description.

**Do NOT flag:**

- `http(s)` **image URLs supplied by the user** in their own config. That is the user's choice; the `image:` field documents it.
- `file://` hrefs produced by `resolve_image` for absolute local paths.

**Review approach:**

1. Grep the template for `http`, `//`, `@import`, `fetch(`, `import(`.
2. Generate a chart, open it with networking disabled (or check the artifact/CSP context renders), and confirm nothing is missing.

---

## network-boundary-reviewer

Review changes touching **network access and external processes**. Sanctioned network calls, all to CDS services: `catalog.sesame()` (designation resolver, chart pipeline) and the `annotate.field` queries (VizieR Gaia DR3/Tycho-2, SIMBAD), each gated by `allow_online`/`--offline` and degrading to warnings. The Gaia archive (gea.esac.esa.int) is never contacted; it is blocked in some sandboxes, which is why Gaia data comes through VizieR. The one sanctioned external process is the ASTAP solver in `annotate/solver.py`: list-argv subprocess (never `shell=True`), explicit timeout, and a clear install-hint error when the binary is missing. Everything else is offline by contract, because host applications (astro workflow managers, CI, air-gapped processing boxes) embed this library and must be able to hold it to `allow_online=False`.

**FLAG (P1) when a PR:**

- Adds any network call outside the sanctioned set above, or any code path reaching them without an `allow_online` gate. Trace from `resolve_objects` and `annotate.model.build_model` down.
- Adds a subprocess call outside `annotate/solver.py`, or weakens the solver invocation (`shell=True`, missing timeout, unquoted paths).
- Performs network I/O at import time or during `Catalog()` construction. Catalog data is bundled; construction must work in an offline sandbox.
- Removes or bypasses the CLI `--offline` flag's effect.

**FLAG (P2) when a PR:**

- Adds a network call without an explicit `timeout=`. `urllib` defaults to hanging.
- Catches network failures in a way that raises instead of warning. The contract: a failed lookup produces a warning string and a skipped object, never a crashed chart.
- Adds a runtime dependency for HTTP (requests, httpx). `urllib.request` is sufficient for one GET; new deps ripple into every host app.

**Do NOT flag:**

- Network use in `tests/` explicitly marked as online tests, or in repo tooling/scripts that are not part of the package.

---

## catalog-data-reviewer

Review changes to **bundled catalog data and its parsing** (`catalog.py`, `resources.py`, `src/uranometria/data/`, `src/uranometria/assets/`). The catalogs are package resources that ride inside the wheel; host apps never see the repo checkout.

**Rules to enforce:**

1. **`importlib.resources` only.** All bundled data loads through `resources.py` helpers. FLAG (P1) any `Path(__file__).parent`, `os.path.dirname(__file__)`, or open-by-relative-path for package data. It breaks in wheels and frozen builds. (`__file__` in `tests/` is fine.)
2. **New data files go under `src/uranometria/data/` or `assets/`** so `uv_build` packages them. FLAG (P2) a data file added anywhere else, and require the PR to show the file present in a built wheel (`uv build` + zip listing) if packaging config was touched.
3. **Respect OpenNGC's quirks.** Parser changes must preserve the existing handling: `Dup` rows resolve through their NGC/IC cross-reference, `NonEx` rows are dropped, the `M` column is zero-padded (`'045'`), Caldwell arrives both via `Identifiers` (`"C 014"`) and as addendum rows (`C009`, `C014`, `C041`, `C099`), and M40/M45/M102 exist only via the addendum. FLAG (P2) any parser change without tests touching at least the quirk it modifies.
4. **Designation normalization is load-bearing.** `_norm()` maps user spellings to keys (`"sh 2-142"` → `SH2142`, `"Caldwell 9"` → `C9`). Changes need parametrized test rows for both the new form and the existing forms, since regressions here silently resolve to the wrong object.
5. **Attribution travels with data.** A new bundled catalog needs its source and license added to the README's Data & licenses section and, if it renders on the page, the chart footer. FLAG (P2) if missing. Refreshing an existing catalog snapshot should note the retrieval date in the PR.

**Do NOT flag:**

- Large diffs in the data files themselves when the PR says it is a catalog refresh; eyeball row counts and format, not contents.

---

## public-surface-reviewer

Review changes to the **public contract**: the YAML config schema, the library API (`generate`, `render`, `resolve_objects`, `SkymapError`), and the CLI. Host applications build configs programmatically against these; the README's Library API section is the promise they integrate against.

**Rules to enforce:**

1. **Config keys are forever-ish.** A new config key needs: README documentation, an entry or comment in `examples/skymap.yaml`, and a test. Renaming or repurposing an existing key is a breaking change and needs an explicit deprecation story in the PR, not a silent swap. FLAG (P1) for silent breaks, P2 for undocumented additions.
2. **The warnings contract holds.** `generate`/`render` return warnings as a list of plain strings; per-object failures degrade (skip the object or drop its photo) rather than raise; `SkymapError` is reserved for "no chart is possible at all". FLAG (P1) any new raise on a per-object problem or any change to the return shapes.
3. **The library does not print.** Only `cli.py` writes to stdout/stderr. FLAG (P2) any `print()` or logging setup added under `src/uranometria/` outside the CLI.
4. **CLI flags mirror config.** A behavior toggle exposed as a flag must also exist as a config key (`--mirror` / `mirror:` is the pattern), so programmatic users are not second-class. FLAG (P2).
5. **Version discipline.** Behavior visible in output (orientation, layout, resolution behavior) or API surface changed → `version` bumps in `pyproject.toml` **and** `__init__.__version__`, together, in the same PR. FLAG (P2) if either is missed; they have drifted apart before.

**Do NOT flag:**

- Purely internal refactors (`chart.py` internals, private helpers) with no config/API/CLI-visible effect.
- Visual styling tweaks to the generated page. The page's look is not a compatibility surface; its data attributes and config inputs are.

---

# Guidelines

A reviewer pack tuned for **uranometria**: a small pure-Python library and CLI that renders self-contained interactive HTML star charts from bundled astronomical catalogs.

## How the pack runs

**This file is consumed BY the `pr-review-loop` skill — do not run these reviewers directly.** The skill owns posting findings as PR comments, validation, per-agent retirement, CI gating, and exit conditions. Hand-spawning agents from this file skips all of that and breaks the PR audit trail.

Each reviewer runs independently and reports findings without coordination. A reviewer's silence is not an endorsement; it means nothing in its scope changed.

**Per-reviewer file scope:**

| Reviewer | Files in scope |
|----------|----------------|
| `test-coverage-reviewer` | `src/**/*.py`, `tests/**/*.py` |
| `celestial-math-reviewer` | `src/uranometria/chart.py`, `catalog.py` (angles), hemisphere logic in `page.py`/`core.py` |
| `markup-safety-reviewer` | `src/uranometria/page.py`, `chart.py` (SVG emission) |
| `self-contained-output-reviewer` | `src/uranometria/page.py`, `chart.py`, `assets/` |
| `network-boundary-reviewer` | `src/uranometria/catalog.py`, `core.py`, `cli.py`, `annotate/` |
| `catalog-data-reviewer` | `src/uranometria/catalog.py`, `resources.py`, `data/`, `assets/`, packaging config |
| `public-surface-reviewer` | `core.py`, `cli.py`, `__init__.py`, `README.md`, `examples/`, `pyproject.toml` |

Skip reviewers whose file scope doesn't match the PR diff.

**Mutation testing runs in a worktree.** Any reviewer that mutates source to
probe test coverage MUST do so in its own `git worktree` of the commit under
review, never in the shared checkout — concurrent sessions edit that checkout,
and `git checkout --` restores have twice wiped in-flight uncommitted work.
Read-only reviewers may use the shared checkout but should verify claims
against the committed blobs (`git show <sha>:<path>`) when the tree is dirty.

## Tooling assumed in CI

CI (`.github/workflows/ci.yml`) runs on every PR and push to master, and `master` is branch-protected on the `check` job:

- `uv run black --check src tests` — formatting (line length 100, configured in `pyproject.toml`)
- `uv run pytest -q` — unit tests

Reviewers do not re-litigate formatting; black owns it. There is currently no ruff, mypy, or coverage tracking. Do **not** treat their absence as a blocking finding; a reviewer may raise adopting one as a **P3** suggestion at most, once, with a beads ticket.

Useful manual verification for UI-affecting changes: `rodney` (headless Chrome CLI) drives the generated page well — load the HTML, assert on DOM state, screenshot. Layout claims in PR descriptions ("no page scrollbar", "sidebar scrolls independently") should come with a rodney measurement or equivalent.

## Severity convention

Every finding is tagged with a beads-style priority:

| Priority | Disposition | Examples |
|----------|-------------|----------|
| **P1** | Blocking — must fix before merge | Chirality/sign change without an orientation test, unescaped user string in markup, network call outside the `allow_online` gate, external resource in generated HTML, silent config-key break |
| **P2** | Should fix in this PR | Missing test for a new parser branch, hard-coded geometry constant, missing `timeout=`, undocumented config key, version bump missed in one of the two places |
| **P3** | Advisory — deferrable with a beads ticket | Tooling adoption suggestions, page-weight nits, naming/clarity |

**Default severity per reviewer:** `celestial-math-reviewer`, `markup-safety-reviewer`, `self-contained-output-reviewer`, `network-boundary-reviewer`: **P1** for their FLAG-P1 lists, otherwise P2. `test-coverage-reviewer`, `catalog-data-reviewer`, `public-surface-reviewer`: **P2** by default with listed P1 escalations.

A reviewer may promote or demote a specific finding from its default, but must state why.

## Output format

```
[<reviewer>] [<severity>] <one-line title>

File: path/to/file.py:LINE
Quote:
    <1-5 lines of code or text being flagged>

Issue: <one or two sentences on what's wrong>
Suggested fix:
    <concrete diff or rewritten code/text>
Reason (optional): <only if not obvious>
```

Example:

```
[celestial-math-reviewer] [P1] New horizontal sign convention outside ra_sign()

File: src/uranometria/chart.py:186
Quote:
    x = CX - r * math.sin(a) if not self.south else CX + r * math.sin(a)

Issue: Reintroduces an inline chirality decision instead of using self.sign /
ra_sign(). This is exactly the pattern that shipped the v0.2.0 mirrored-sky
bug, and it ignores the mirror option entirely.
Suggested fix:
    x = CX + self.sign * r * math.sin(a)
```

## Deferring findings with beads

To defer a P2 or P3 finding to a follow-up:

1. Create a beads ticket capturing reviewer name, severity, file, and quote.
2. Link the ticket in the PR description or as a reply to the reviewer's comment.
3. The reviewer accepts the deferral only when the beads ticket exists.

**P1 findings are not deferrable** — they must be fixed in-PR.
