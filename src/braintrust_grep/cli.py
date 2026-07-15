"""``btgrep`` command-line interface.

Subcommands stream JSONL on stdin/stdout so they pipe:

    btgrep search ... | btgrep enrich ... | btgrep export -o out.csv

Diagnostics go to stderr. ``btgrep hunt`` runs search|enrich|export from a spec.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from . import __version__
from .client import BtqlClient
from .config import ClientOptions
from .enrich import enrich as enrich_rows
from .errors import BtgrepError
from .export import add_urls, parse_columns, to_csv, to_jsonl
from .metadata import MetadataObjectEmpty
from .predicates import AllOf, AnyOf, EmptyOrMissing, Predicate, Regex
from .projects import resolve_project_id
from .search import resolve_window
from .search import search as run_search

app = typer.Typer(
    add_completion=True,
    no_args_is_help=True,
    help="Regex & structural search over Braintrust logs (BTQL has no regex).",
)


def err(msg: str) -> None:
    typer.echo(msg, err=True)


def _client() -> BtqlClient:
    try:
        return BtqlClient(ClientOptions.from_env())
    except BtgrepError as exc:
        err(f"error: {exc}")
        raise typer.Exit(2) from exc


def _project_id(name: str | None, project_id: str | None) -> str:
    if project_id:
        return project_id
    if not name:
        err("error: provide --project NAME or --project-id ID")
        raise typer.Exit(2)
    try:
        return resolve_project_id(name)
    except BtgrepError as exc:
        err(f"error: {exc}")
        raise typer.Exit(2) from exc


def _resolve_for_links(project: str) -> str | None:
    """Resolve a project name to its id for deep-links; None (with a warning) on failure."""
    try:
        return resolve_project_id(project)
    except BtgrepError as exc:
        err(f"warning: no deep-link url column — could not resolve project id ({exc})")
        return None


def _read_pattern(spec: str) -> str:
    """A leading '@' means read the raw regex from a file (dodges shell quoting)."""
    if spec.startswith("@"):
        return Path(spec[1:]).read_text(encoding="utf-8").rstrip("\n")
    return spec


def _build_regex(items: list[str], ignore_case: bool) -> list[Regex]:
    flags = re.IGNORECASE if ignore_case else 0
    out = []
    for item in items:
        if "=" not in item:
            err(f"error: --regex must be FIELD=PATTERN, got {item!r}")
            raise typer.Exit(2)
        field, pattern = item.split("=", 1)
        out.append(Regex(field.strip(), _read_pattern(pattern), flags))
    return out


def _build_metadata(items: list, marker: str | None) -> list[MetadataObjectEmpty]:
    """Build metadata predicates from CLI strings ("FIELD:k1,k2") or spec dicts.

    A dict entry ({field, keys, marker?, require_marker?}) carries its own marker;
    string entries use the shared ``marker`` argument (from --metadata-marker).
    """
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(
                MetadataObjectEmpty(
                    item["field"],
                    tuple(item["keys"]),
                    marker=item.get("marker"),
                    require_marker=item.get("require_marker", True),
                )
            )
            continue
        if ":" not in item:
            err(f"error: --metadata-empty must be FIELD:key1,key2 — got {item!r}")
            raise typer.Exit(2)
        field, keys = item.split(":", 1)
        out.append(
            MetadataObjectEmpty(
                field.strip(),
                tuple(k.strip() for k in keys.split(",")),
                marker=marker or None,
                require_marker=bool(marker),
            )
        )
    return out


def _build_predicate(
    regexes: list[str],
    empties: list[str],
    metadata: list,
    *,
    metadata_marker: str | None = None,
    any_mode: bool,
    ignore_case: bool,
) -> Predicate:
    preds: list[Predicate] = []
    preds.extend(_build_regex(regexes, ignore_case))
    preds.extend(EmptyOrMissing(f.strip()) for f in empties)
    preds.extend(_build_metadata(metadata, metadata_marker))
    if not preds:
        err("error: provide at least one --regex, --empty, or --metadata-empty")
        raise typer.Exit(2)
    return AnyOf(*preds) if any_mode else AllOf(*preds)


def _parse_match(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for item in items:
        field, text = item.split("=", 1) if "=" in item else ("output", item)
        out.append((field.strip(), text))
    return out


def _read_jsonl(path: str | None) -> list[dict[str, Any]]:
    if path:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _emit_rows(rows: list[dict[str, Any]], output: str | None) -> None:
    out = output or sys.stdout
    n = to_jsonl(rows, out)
    err(f"{n} row(s) written.")


@app.command()
def search(
    project: Annotated[str | None, typer.Option("--project", "-p", help="Project name")] = None,
    project_id: Annotated[str | None, typer.Option(help="Project id (skips name lookup)")] = None,
    since: Annotated[str, typer.Option(help="Look-back window, e.g. 14d/36h/ISO/epoch-ms")] = "14d",
    until: Annotated[str, typer.Option(help="End of window (default now)")] = "now",
    match_fulltext: Annotated[
        list[str] | None,
        typer.Option("--match-fulltext", help="Server MATCH prefilter FIELD=TEXT (repeatable)"),
    ] = None,
    where: Annotated[list[str] | None, typer.Option(help="Raw BTQL filter (repeatable)")] = None,
    regex: Annotated[
        list[str] | None, typer.Option("--regex", help="Local regex FIELD=PATTERN (or FIELD=@file)")
    ] = None,
    empty: Annotated[
        list[str] | None, typer.Option("--empty", help="Field empty-or-missing (repeatable)")
    ] = None,
    metadata_empty: Annotated[
        list[str] | None,
        typer.Option("--metadata-empty", help="JSON-in-field key(s) empty, FIELD:key1,key2"),
    ] = None,
    metadata_marker: Annotated[
        str | None,
        typer.Option(
            "--metadata-marker",
            help="Marker preceding the JSON block for --metadata-empty (e.g. '=== METADATA ==='). "
            "Omit if the field is already JSON.",
        ),
    ] = None,
    any_mode: Annotated[
        bool, typer.Option("--any", help="OR the predicates instead of AND")
    ] = False,
    ignore_case: Annotated[
        bool, typer.Option("--ignore-case", "-i", help="Case-insensitive regex")
    ] = False,
    select: Annotated[
        list[str] | None, typer.Option("--select", help="Override selected columns")
    ] = None,
    extra_select: Annotated[
        list[str] | None, typer.Option("--extra-select", help="Add columns beyond auto-derived")
    ] = None,
    max_rows: Annotated[
        int | None, typer.Option("--max-rows", help="Stop after scanning N rows")
    ] = None,
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="Output file (default stdout)")
    ] = None,
) -> None:
    """Scan a project + window and emit matching rows as JSONL."""
    predicate = _build_predicate(
        regex or [],
        empty or [],
        metadata_empty or [],
        metadata_marker=metadata_marker,
        any_mode=any_mode,
        ignore_case=ignore_case,
    )
    window = resolve_window(since, until)
    pid = _project_id(project, project_id)
    err(f"searching {project or pid} — {window[0]} .. {window[1]}")
    with _client() as client:
        try:
            rows = list(
                run_search(
                    client,
                    pid,
                    window=window,
                    predicate=predicate,
                    match=_parse_match(match_fulltext or []),
                    where=where or [],
                    select=select,
                    extra_select=extra_select or [],
                    max_scan=max_rows,
                )
            )
        except BtgrepError as exc:
            err(f"error: {exc}")
            raise typer.Exit(1) from exc
    _emit_rows(rows, output)


@app.command()
def enrich(
    project: Annotated[str | None, typer.Option("--project", "-p")] = None,
    project_id: Annotated[str | None, typer.Option()] = None,
    root_field: Annotated[
        list[str] | None, typer.Option("--root-field", help="Dotted path on root span (repeatable)")
    ] = None,
    bucket: Annotated[str, typer.Option(help="Time-bucket size for batched lookups")] = "1h",
    batch: Annotated[int, typer.Option(help="Max root_span_ids per IN query")] = 60,
    input_file: Annotated[
        str | None, typer.Option("--input", "-i", help="Input JSONL (default stdin)")
    ] = None,
    output: Annotated[str | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Join fields from each trace's root span onto matched rows.

    Provide the dotted paths you want with --root-field, e.g.
    ``--root-field input.doc_id --root-field input.user_id``.
    """
    if not root_field:
        err("error: enrich needs at least one --root-field (e.g. input.doc_id)")
        raise typer.Exit(2)
    rows = _read_jsonl(input_file)
    pid = _project_id(project, project_id)
    with _client() as client:
        try:
            rows = enrich_rows(
                client,
                rows,
                project_id=pid,
                root_fields=root_field,
                bucket=bucket,
                batch=batch,
                progress=err,
            )
        except BtgrepError as exc:
            err(f"error: {exc}")
            raise typer.Exit(1) from exc
    _emit_rows(rows, output)


@app.command()
def export(
    output: Annotated[str, typer.Option("--output", "-o", help="Output file")],
    fmt: Annotated[str, typer.Option("--format", help="csv or jsonl")] = "csv",
    input_file: Annotated[
        str | None, typer.Option("--input", "-i", help="Input JSONL (default stdin)")
    ] = None,
    org: Annotated[
        str | None, typer.Option(help="Org slug for deep-links (or $BRAINTRUST_ORG_NAME)")
    ] = None,
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Project slug for deep-links")
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option(help="Project id for deep-links (auto-resolved from --project if omitted)"),
    ] = None,
    columns: Annotated[
        list[str] | None,
        typer.Option("--columns", help="CSV columns as 'header=path' or 'path' (default: auto)"),
    ] = None,
) -> None:
    """Write matched/enriched rows to CSV (with span deep-links) or JSONL.

    A `url` deep-link column is added when --org and --project are given; the
    project id is resolved from --project unless you pass --project-id. Columns
    default to the scalar fields present on the rows; pass --columns to control
    them, including nested paths like output or span_attributes.name.
    """
    rows = _read_jsonl(input_file)
    import os

    org = org or os.environ.get("BRAINTRUST_ORG_NAME")
    if org and project:
        pid = project_id or _resolve_for_links(project)
        if pid:
            rows = add_urls(rows, org=org, project=project, project_id=pid)
    if fmt == "jsonl":
        n = to_jsonl(rows, output)
    else:
        n = to_csv(rows, output, parse_columns(columns) if columns else None)
    err(f"{n} row(s) -> {output}")


@app.command()
def hunt(
    spec_file: Annotated[str, typer.Option("--spec", help="YAML/JSON spec file")],
    project: Annotated[str | None, typer.Option("--project", "-p")] = None,
    project_id: Annotated[str | None, typer.Option()] = None,
    since: Annotated[str | None, typer.Option()] = None,
    until: Annotated[str | None, typer.Option()] = None,
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output CSV/JSONL")
    ] = "hunt_out.csv",
    fmt: Annotated[str, typer.Option("--format")] = "csv",
) -> None:
    """Run search|enrich|export end-to-end from a declarative spec."""
    spec = _load_spec(spec_file)
    pid = _project_id(project or spec.get("project"), project_id)
    window = resolve_window(since or spec.get("since", "14d"), until or spec.get("until", "now"))
    preds = spec.get("predicates", {})
    predicate = _build_predicate(
        preds.get("regex", []),
        preds.get("empty", []),
        preds.get("metadata_empty", []),
        any_mode=(preds.get("mode", "all") == "any"),
        ignore_case=bool(preds.get("ignore_case", False)),
    )
    match = _parse_match(spec.get("prefilter", {}).get("match", []))
    org = spec.get("org")
    import os

    org = org or os.environ.get("BRAINTRUST_ORG_NAME")

    err(f"hunt: {project or pid} — {window[0]} .. {window[1]}")
    with _client() as client:
        rows = list(
            run_search(
                client,
                pid,
                window=window,
                predicate=predicate,
                match=match,
                extra_select=spec.get("select_extra", []),
            )
        )
        enr = spec.get("enrich")
        if enr and enr.get("root_fields"):
            err(f"{len(rows)} match(es); enriching…")
            rows = enrich_rows(
                client,
                rows,
                project_id=pid,
                root_fields=enr["root_fields"],
                bucket=enr.get("bucket", "1h"),
                batch=int(enr.get("batch", 60)),
                progress=err,
            )
    proj_slug = project or spec.get("project")
    if org and proj_slug:
        rows = add_urls(rows, org=org, project=proj_slug, project_id=pid)
    columns = spec.get("export", {}).get("columns")
    cols = parse_columns(columns) if columns else None
    n = to_jsonl(rows, output) if fmt == "jsonl" else to_csv(rows, output, cols)
    err(f"wrote {n} row(s) -> {output}")


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


def _load_spec(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as exc:
            err("error: reading a YAML spec needs pyyaml (`pip install braintrust-grep[yaml]`).")
            raise typer.Exit(2) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
