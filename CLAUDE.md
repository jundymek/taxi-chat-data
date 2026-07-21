# Project conventions

## Commits and PRs

**Never add AI-attribution footers.** Commit messages and PR bodies must not
contain `Co-Authored-By: Claude ...`, `🤖 Generated with [Claude Code]`, or any
equivalent. This overrides default tooling behaviour. A message ends on
substance — the last line is the last thing worth saying about the change.

Commit messages explain *why*, not just *what*. Where a change has a non-obvious
consequence (a hidden contract, a string shared across services, a decision that
looks wrong without context), say so in the body.

## Language

- **English**: all code, comments, identifiers, commit messages, PR bodies,
  README, and every user-facing string in the app.
- **Polish**: one learning note per task under `docs/learn/<task>.md`. These are
  the owner's study material — concise but substantive, covering what was
  non-obvious rather than restating the diff.

The app answers in whatever language the user's question was asked in; the UI
itself is English.

## Working agreements

- Per-task PRs into a phase branch, then one umbrella PR into `master`.
- TDD where practical: show real test output rather than asserting success.
- Verify before claiming done — run the command, read the output, report what it
  actually said.

## Gotchas worth knowing

- `data/chroma` is a materialised copy of `genai/examples.yml` and the dbt model
  docs. Editing either does **not** refresh it — run `python -m genai.indexer`.
- `dbt/models/marts/_marts__models.yml` is the schema context fed to the NL2SQL
  model, not just human documentation. An undocumented column is a column the
  model has to guess the name of, so document measures too, not only the columns
  that carry dbt tests.
- Ollama runs on the **host**, never in a container (no GPU on macOS, ~10 GB of
  re-downloaded models). Containers reach it via `host.docker.internal`.
- `uvicorn --reload` only reloads inside an already-running process. After
  changing code, confirm the process on `:8000` actually predates the edit
  before debugging "my change did nothing".
