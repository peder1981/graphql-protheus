# GraphQL Core Engine (Protheus)

Dynamic GraphQL server over the Protheus data dictionary (SX2/SX3/SX9),
running as a TLPP AppServer REST entry point.

## Endpoint

- `GET /graphql` — schema type names (deny-list applied)
- `GET /graphql?type=<TABLE>` — full type detail for one table (fields + relations)
- `GET /graphql?query=<url-encoded GraphQL text>` — execute a query

## Example

```
{ SA1(limit: 5, filter: [{field: "A1_COD", op: "eq", value: "000001"}]) {
    A1_COD
    A1_NOME
    SC5 { C5_NUM }
} }
```

## Mutations

`createTABLE`/`updateTABLE`/`deleteTABLE` are exposed only for tables
listed in `config/graphql-config.json`'s `allowMutations` (empty by
default — nothing is writable until an admin opts a table in). Delete is
always soft (`D_E_L_E_T_ = '*'`), never a real row removal.

```
mutation { createSA1(input: {A1_COD: "000123", A1_LOJA: "01", A1_NOME: "Foo"}) {
    A1_COD
    A1_NOME
} }
```

**Known limitation**: See `docs/architecture.md` for a concurrency caveat on `create` mutations.

See `docs/architecture.md` and
`docs/superpowers/specs/2026-08-14-graphql-mutations-design.md`.

## Configuration

See `docs/configuration.md`. **`compile.sh`/`deploy-rpo.sh` only ever handle
compiled `.tlpp` sources** — `custom/backoffice/graphql/config/graphql-config.json`
must be copied to the AppServer's `RootPath` separately (check
`appserver.ini`'s `[P12] RootPath=` — `MemoRead()` resolves relative paths
against this, not `SourcePath`, confirmed by testing both). Without it, the
deny-list silently falls back to empty and every table becomes visible —
confirmed against a live server during development.

## Architecture

See `docs/architecture.md` and
`docs/superpowers/specs/2026-08-13-graphql-core-engine-design.md`.

## Tests

TIR (Python e2e) under `tests/tir/`. Run with `pytest tests/tir/ -v`
against a running Protheus AppServer with this RPO deployed.

## Sub-project roadmap

This is sub-projects 1-2 of 6: Core Engine + Mutations (this repo) → Auth →
Field Hooks → SDK Generator → Console PO-UI. See the design specs for the
full roadmap and how each later sub-project plugs into this engine.
