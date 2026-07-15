# braintrust-grep

![CI](https://github.com/aflansburg/braintrust-grep/actions/workflows/ci.yml/badge.svg)
![coverage](https://img.shields.io/badge/coverage-82%25-brightgreen)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Tool for regex and structural search over [Braintrust](https://www.braintrust.dev) logs.

Braintrust's query language (BTQL) has **no regex** in log filters, and its
`LIKE`/substring operator can **silently match nothing on structured (JSON-object)
fields**.

So the reliable pattern I've found is is: prefilter server-side with `MATCH`, pull
logs for scoped to a `created` window, then match locally in Python.

`braintrust-grep` does this for you while also handling the rate limit, query timeout, gzip redirects,
pagination, and span deep-linking for you.

I built this while hunting down hallucinations and other discrepancies in an 'AI' (LLM) powered extraction pipeline.

## Install

You can install on Github today, PyPi package coming soon.

**As a CLI tool**

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
export BRAINTRUST_ORG_NAME=...    # optional, for deep-links !!!! Case Sensitive it seems !!!!
```

> Once published to PyPI this becomes `uv tool install braintrust-grep` /
> `uvx braintrust-grep`. The `braintrust-grep` command is an alias for `btgrep`,
> so `uvx braintrust-grep` resolves without `--from`.

## Quickstart (CLI)

```bash
# Find spans whose output matches a regex, last 14 days (shorter time intervals are more ideal):
btgrep search -p my-project --since 14d --regex 'output=timeout|refused'

# AND several field-scoped predicates (regex + "key empty or missing"):
btgrep search -p my-project --since 7d \
    --match-fulltext output=evidence \
    --regex 'input.raw_text=user_\d+' \
    --empty output.result
```

Subcommands stream JSONL on stdin/stdout and diagnostics go to stderr.

It's a subcommand pattern we decided to support common in pipeline tooling like `jq` or the OG `grep | sed | awk`.

```bash
btgrep search -p my-project --since 14d --regex 'output=foo' \
  | btgrep enrich -p my-project --root-field input.doc_id --root-field input.patient_id \
  | btgrep export -o out.csv -p my-project --org MyOrg   # project id auto-resolved
```

You can write up a declarative spec (copy one from [`examples/`](examples/) and
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
    MetadataObjectEmpty("input.raw_text", keys=("pages", "documentdata"),
                        marker="=== METADATA ==="),
)
matches = list(search(
    client, pid, window=window, predicate=predicate,
    match=[("output", "evidence"), ("output", "symptoms")],  # server MATCH prefilter
))
enriched = enrich(client, matches, project_id=pid,
                  root_fields=["input.doc_id", "input.patient_id"])
```

## Predicates

- `Regex(field, pattern, flags)`: regex over a dotted field (non-strings are JSON-serialized first, so you can match structure). `field="*"` matches the whole row.
- `EmptyOrMissing(field)`: true when the key is absent **or** the value is `""`/`[]`/`{}`/`null`. (Regex can't express "missing".)
- `MetadataObjectEmpty(field, keys, marker=None)`: parses JSON found in `field` — a JSON column, a JSON string, or a block embedded in text after an optional `marker` (e.g. the field may be raw text with a preceding `"=== METADATA ==="`) — and matches when every named key is empty-or-missing. Schema-agnostic: set `field`/`keys`/`marker` to your own.
- `AllOf` / `AnyOf` / `Not`: compose them.

## Constraints & gotchas (why this library exists)

- **30-second query timeout.** A single query over 30 seconds will return HTTP 504. Fast-path to staying under that: `created`-range + `MATCH` + cursor pagination. Wide `id IN`/`root_span_id IN`/`LIKE`/span-name scans will blow your rate limit budget. Enrichment uses narrow time-bucketed `IN` batches.
- **`LIKE` is blind to structured fields.** `output LIKE '%x%'` returns 0 when `output` is a JSON object. Use `MATCH`. The query builder warns if you `LIKE` a structured field.
- **Rate limit ~20 requests / 60s per org** (HTTP 429). The client paces itself and honors `Retry-After`; retries `408/429/500/502/503/504` with capped backoff.
- **Large results 303-redirect to a gzipped object**: handled transparently.
- **Per-span payloads up to 20 MB** (`raw_text` can be a whole document). The scan selects only the columns your predicates read. Never `select: *`.
- **Row `id` ≠ `span_id`.** Deep-links need `r=<root_span_id>&s=<span_id>`, not the row id. `span_deeplink()` takes care of this for you.

## Configuration (env)

| Var | Purpose |
|-----|---------|
| `BRAINTRUST_API_KEY` | Auth (required) |
| `BRAINTRUST_ORG_NAME` | Org slug for deep-links |
| `BRAINTRUST_BTQL_URL` | Override the BTQL endpoint |

`ClientOptions` exposes `min_request_interval`, `max_retries`, `page_size`,
`retry_statuses`, backoff knobs, etc. `.env` is loaded automatically if
`python-dotenv` is installed (never required).

## Development

```bash
uv sync --extra dev                 # install with dev + test deps
uv run ruff check . && uv run ruff format --check .
```

### Running the tests

The suite is offline. No Braintrust credentials or network required. HTTP is
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

## TBD

Async client; parallel bucket fetching (the rate limit makes concurrency
low-value); result caching/resume; non-`project_logs` sources (experiments,
datasets); a custom-predicate plugin system beyond `--spec`; an interactive TUI.

## Contributing

Issues and PRs welcome. Please:

1. Fork and branch off `main`.
2. `uv sync --extra dev`, then keep `ruff check`, `ruff format`, and `pytest` green.
3. Add a test for any behavior change (the suite is offline — mock HTTP with
   `httpx.MockTransport` and time with `FakeClock`; see `tests/conftest.py`).
4. Open a PR describing the change and, for a bug fix, the failing case it covers.

## License

MIT — see [LICENSE](LICENSE).
