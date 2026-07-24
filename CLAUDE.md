# uranometria — project conventions

## Beads (issue tracker)

Beads state lives in `.beads/` (JSONL-only mode, no dolt). Cross-branch JSONL
edits turn into merge pain, so:

**Beads-only changes always commit and push directly to `master`**, even while
feature branches or PRs are open. Never route a `.beads/` change through a PR
branch, and never let ticket filing wait on a code review. If you're on a
feature branch when tickets change, commit `.beads/` to master (stash or
worktree if needed) and keep code commits separate from beads commits.

A mixed commit (code + beads) is a mistake; split it.

## Everything else

- Tests and formatting gate merges: `uv run black --check src tests` and
  `uv run pytest` (CI runs both; master is branch-protected on the `check` job).
- Review conventions live in `AGENT-REVIEWERS.md` (consumed by pr-review-loop).
- Versions bump in `pyproject.toml` AND `src/uranometria/__init__.py` together,
  with a matching entry added to `CHANGELOG.md`, all in the same PR.
- The generated chart page stays a single self-contained HTML file: no external
  resources fetched at render time (user-clicked links are fine).
- Network access in the library is gated behind `allow_online`; ASTAP is the
  only external process, confined to `annotate/solver.py`.
