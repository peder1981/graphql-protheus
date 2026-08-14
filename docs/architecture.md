# Architecture

Request pipeline:

```
GET /graphql --> GQLSERVICE (entrypoints/service.entrypoint.tlpp)
             --> GqlLexer + GqlParser (core/lexer.tlpp, core/parser.tlpp)
             --> GqlValidator (core/validator.tlpp)
             --> GqlExecutor (core/executor.tlpp)
                 --> GqlQueryBuilder (core/query-builder.tlpp)
                 --> GqlDictionaryReader (core/dictionary-reader.tlpp)
             --> JSON response
```

Schema is never hand-written: `GqlSchemaProvider` (core/schema-provider.tlpp)
builds GraphQL types lazily from SX2 (tables) and SX3 (fields), and
relationship fields from SX9. Tables/fields are filtered by
`GqlAccessControl` (core/access-control.tlpp) against
`config/graphql-config.json`'s deny-lists before anything is cached.

Per-user permission checks are out of scope for this sub-project; the Auth
sub-project will add them, likely as another method on `GqlAccessControl`.

## Mutations

`GqlMutationExecutor` (core/mutation-executor.tlpp) is a parallel write
pipeline alongside the read executor, sharing the same lexer/parser and
the same `GqlDictionaryReader`/`GqlQueryBuilder`. It writes via
`TCSqlExec()` — **not** `TCQuery`, which crashes uncatchably on anything
but `SELECT` in this environment (confirmed empirically; see the plan's
Global Constraints for the full investigation) — and re-selects the
affected row through the existing `GqlExecutor:resolveTableField()` so
response shaping (aliases, nested selections) is never duplicated.

A table is writable only if it's in `allowMutations` (config) AND still
passes the read-path deny-list — the two gates combine, neither alone is
sufficient. `GqlInputValidator` checks required/type/length against SX3
metadata before any SQL runs. Delete is always soft
(`D_E_L_E_T_ = '*'`), matching how every query already filters reads.

Unknown or denied input fields are currently silently ignored, not
rejected with an explicit error: `GqlValidator` is never invoked on the
mutation path, so a field name that isn't part of the dictionary-driven
SET/INSERT field lists is simply excluded when those lists are built —
it never reaches SQL, so this isn't a security hole, but it does diverge
from normal GraphQL semantics (an unknown input-object field should be a
validation error). Closing this is deferred to a future sub-project's
per-field mutation argument validation.

### Known limitation: Concurrency and `R_E_C_N_O_` assignment

`create` mutations assign `R_E_C_N_O_` (the table's physical primary key on
this raw-SQL write path, since normal ISAM/DBAccess auto-assignment is
bypassed) via a `MAX(R_E_C_N_O_)+1` SQL subquery. This is **not safe under
concurrent writes** — two simultaneous `create` calls against the same table
can race and attempt to insert the same `R_E_C_N_O_` value, causing a
primary key collision.

Both a real Postgres sequence/IDENTITY column and a same-statement
advisory-lock approach were investigated and found unavailable/ineffective
in this environment. Closing this gap requires a database migration (adding
real sequences/IDENTITY columns to Protheus dictionary tables) or a
server-side stored procedure — both out of scope for this sub-project.

**Current safety guarantee**: Safe for single-request and low-concurrency
use (e.g., this sub-project's own testing). **Not safe** for concurrent
production traffic on the same table.

See `custom/backoffice/graphql/core/mutation-builder.tlpp`'s `buildInsert()`
Protheus.doc header for the full technical analysis.
