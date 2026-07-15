# Examples

Both examples are **specs** you run with `btgrep hunt`. Values marked `<-- ...`
(project, org, patterns, fields) are placeholders — replace them with paths that
exist in *your* Braintrust logs. Deep-link URLs need `BRAINTRUST_ORG_NAME` (or
`org:` in the spec); everything else needs only `BRAINTRUST_API_KEY`.

## `find_errors.yaml` — generic starter (adapt & run)

The minimal shape: find spans whose `output` matches an error regex in the last
7 days. Change four values and go.

```bash
export BRAINTRUST_API_KEY=...
btgrep hunt --spec examples/find_errors.yaml -o errors.csv
```

## `symptoms_hunt.yaml` — real-world template (advanced features)

A worked case study showing everything at once: a `MATCH` prefilter, a
multi-field **AND** (an `output` regex **and** a structural "METADATA block is
empty" check), trace **enrichment** (pulling `doc_id`/`patient_id` from the root
span), and a custom CSV column set with span deep-links.

It targets a specific project + log schema, so it **won't run as-is** — it's a
template to adapt. End to end:

```bash
export BRAINTRUST_API_KEY=...
export BRAINTRUST_ORG_NAME=your-org-slug
btgrep hunt --spec examples/symptoms_hunt.yaml -o symptoms.csv
```

The equivalent explicit pipeline (same result, piped subcommands):

```bash
btgrep search -p your-project --since 14d \
    --match-fulltext output=evidence --match-fulltext output=symptoms \
    --regex 'output=@examples/symptoms.re' \
    --metadata-empty 'input.raw_text:pages,documentdata' \
    --metadata-marker '=== METADATA ===' \
    --extra-select span_attributes \
  | btgrep enrich -p your-project \
      --root-field input.doc_id --root-field input.patient_id \
      --root-field input.object_path \
  | btgrep export -o symptoms.csv -p your-project --org your-org-slug \
      --columns 'created,span_id,span_name=span_attributes.name,doc_id,patient_id,output,url'
```

`output=@examples/symptoms.re` reads the (gnarly) regex from a file so you don't
fight shell quoting. Run from the repo root so the relative path resolves.
