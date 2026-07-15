# braintrust-grep

![CI](https://github.com/aflansburg/braintrust-grep/actions/workflows/ci.yml/badge.svg)
![coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Regex and structural search over [Braintrust](https://www.braintrust.dev) logs —
with the correctness gotchas baked in.

Braintrust's query language (BTQL) has **no regex** in log filters, and its
`LIKE`/substring operator **silently matches nothing on structured (JSON-object)
fields**. So the reliable pattern is: prefilter server-side with `MATCH`, pull
logs for a `created` window, then match locally in Python. `braintrust-grep` does
exactly that, and handles the rate limit, the 30s query timeout, gzip redirects,
pagination, and correct span deep-links for you.

> Status: v0.1, extracted from real incident-hunting tooling. Sync client, `project_logs` only.

## Install

Not on PyPI yet — install from GitHub.

**As a CLI tool** (isolated, gets you the `btgrep` command):

```bash
uv tool install git+https://github.com/aflansburg/braintrust-grep

# …or run it once without installing:
uvx --from git+https://github.com/aflansburg/braintrust-grep btgrep --help
```

**As a library:**

```bash
uv add "braintrust-grep @ git+https://github.com/aflansburg/braintrust-grep"
```

Then set your credentials:

```bash
export BRAINTRUST_API_KEY=...     # required
export BRAINTRUST_ORG_NAME=...    # optional, for deep-links
```

> Once published to PyPI this becomes `uv tool install braintrust-grep` /
> `uvx braintrust-grep`. The `braintrust-grep` command is an alias for `btgrep`,
> so `uvx braintrust-grep` resolves without `--from`.

## Quickstart (CLI)

```bash
# Find spans whose output matches a regex, last 14 days:
btgrep search -p my-project --since 14d --regex 'output=timeout|refused'

# AND several field-scoped predicates (regex + "key empty or missing"):
btgrep search -p my-project --since 7d \
    --match-fulltext output=evidence \
    --regex 'input.raw_text=user_\d+' \
    --empty output.result
```

Subcommands stream **JSONL on stdin/stdout**, so they pipe. Diagnostics go to stderr.

```bash
btgrep search -p my-project --since 14d --regex 'output=foo' \
  | btgrep enrich -p my-project --root-field input.doc_id --root-field input.patient_id \
  | btgrep export -o out.csv -p my-project --org MyOrg --project-id "$PID"
```

Or run it all from a declarative spec (copy one from [`examples/`](examples/) and
fill in your project/org/patterns):

```bash
btgrep hunt --spec examples/find_errors.yaml -o out.csv
```

Gnarly regex? Put it in a file and reference it with `@`:
`--regex 'output=@pattern.re'` (no shell-quoting pain).

## Python API

```python
from braintrust_grep import (
    BtqlClient, ClientOptions, resolve_project_id, search, enrich,
    AllOf, Regex, MetadataObjectEmpty, resolve_window,
)

client = BtqlClient(ClientOptions.from_env())
pid = resolve_project_id("my-project")
window = resolve_window("14d", "now")

predicate = AllOf(
    Regex("output", r'"symptoms"\s*:\s*\['),
    MetadataObjectEmpty("input.raw_text", keys=("pages", "documentdata")),
)
matches = list(search(
    client, pid, window=window, predicate=predicate,
    match=[("output", "evidence"), ("output", "symptoms")],  # server MATCH prefilter
))
enriched = enrich(client, matches, project_id=pid,
                  root_fields=["input.doc_id", "input.patient_id"])
```

## Predicates

- `Regex(field, pattern, flags)` — regex over a dotted field (non-strings are JSON-serialized first, so you can match structure). `field="*"` matches the whole row.
- `EmptyOrMissing(field)` — true when the key is absent **or** the value is `""`/`[]`/`{}`/`null`. (Regex can't express "missing".)
- `MetadataObjectEmpty(field, keys)` — parses an embedded `=== METADATA === [ {...} ]` block and matches when every named key is empty-or-missing.
- `AllOf` / `AnyOf` / `Not` — compose them.

## Constraints & gotchas (why this library exists)

- **30-second query timeout.** A single query over it returns HTTP 504. Fast-paths that stay under it: `created`-range + `MATCH` + cursor pagination. Wide `id IN`/`root_span_id IN`/`LIKE`/span-name scans blow the budget — enrichment therefore uses **narrow time-bucketed** `IN` batches.
- **`LIKE` is blind to structured fields.** `output LIKE '%x%'` returns 0 when `output` is a JSON object. Use `MATCH`. (This once caused a 650× undercount: 17 vs 11,024.) The query builder warns if you `LIKE` a structured field.
- **Rate limit ~20 requests / 60s per org** (HTTP 429). The client paces itself and honors `Retry-After`; retries `408/429/500/502/503/504` with capped backoff.
- **Large results 303-redirect to a gzipped object** — handled transparently.
- **Per-span payloads up to 20 MB** (`raw_text` can be a whole document). The scan selects only the columns your predicates read — never `select: *`.
- **Row `id` ≠ `span_id`.** Deep-links need `r=<root_span_id>&s=<span_id>`, not the row id. `span_deeplink()` gets this right.

## Configuration (env)

| Var | Purpose |
|-----|---------|
| `BRAINTRUST_API_KEY` | Auth (required) |
| `BRAINTRUST_ORG_NAME` | Org slug for deep-links |
| `BRAINTRUST_BTQL_URL` | Override the BTQL endpoint |

`ClientOptions` exposes `min_request_interval`, `max_retries`, `page_size`,
`retry_statuses`, backoff knobs, etc. `.env` is loaded automatically if
`python-dotenv` is installed (never required).

## Deferred (not in v1)

Async client; parallel bucket fetching (the rate limit makes concurrency
low-value); result caching/resume; non-`project_logs` sources (experiments,
datasets); a custom-predicate plugin system beyond `--spec`; an interactive TUI.

## Development

```bash
uv sync --extra dev                 # install with dev + test deps
uv run ruff check . && uv run ruff format --check .
```

### Running the tests

The suite is **fully offline** — no Braintrust credentials or network. HTTP is
faked with `httpx.MockTransport` and time with a `FakeClock`, so it runs in well
under a second.

```bash
uv run pytest                       # all tests
uv run pytest --cov                 # with a coverage report
uv run pytest -v                    # verbose (list each test)
uv run pytest tests/test_client.py  # one file
uv run pytest -k "retry or gzip"    # tests matching an expression
uv run pytest -x -q                 # stop at first failure, quiet
```

## Contributing

Issues and PRs welcome. Please:

1. Fork and branch off `main`.
2. `uv sync --extra dev`, then keep `ruff check`, `ruff format`, and `pytest` green.
3. Add a test for any behavior change (the suite is offline — mock HTTP with
   `httpx.MockTransport` and time with `FakeClock`; see `tests/conftest.py`).
4. Open a PR describing the change and, for a bug fix, the failing case it covers.

## License

MIT — see [LICENSE](LICENSE).
