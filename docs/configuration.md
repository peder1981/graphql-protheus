# Configuration

`custom/backoffice/graphql/config/graphql-config.json`:

| Key | Type | Meaning |
|---|---|---|
| `denyTables` | array of wildcard strings | Table aliases never exposed, e.g. `"SRH*"` |
| `denyFields` | array of wildcard strings | Field names never exposed, e.g. `"*SENHA*"` |
| `allowMutations` | array of table aliases (no wildcard) | Tables that accept `createTABLE`/`updateTABLE`/`deleteTABLE` mutations; empty by default (all tables read-only) |
| `pagination.defaultPageSize` | number | `limit` used when the query omits it |
| `pagination.maxPageSize` | number | Hard cap on `limit`, even if the query asks for more |
| `schemaCacheTtlSeconds` | number | How long a table's generated type stays cached before automatic rebuild |

Wildcards support `*` as "any run of characters" (applies to `denyTables` and
`denyFields` only; `allowMutations` takes exact table aliases). Denied
tables/fields never appear in introspection or query results, regardless of
query shape. A table requires **both** `allowMutations` entry **and** absence
from `denyTables` to be writable — the two gates combine.
