# Configuration

`custom/backoffice/graphql/config/graphql-config.json`:

| Key | Type | Meaning |
|---|---|---|
| `denyTables` | array of wildcard strings | Table aliases never exposed, e.g. `"SRH*"` |
| `denyFields` | array of wildcard strings | Field names never exposed, e.g. `"*SENHA*"` |
| `pagination.defaultPageSize` | number | `limit` used when the query omits it |
| `pagination.maxPageSize` | number | Hard cap on `limit`, even if the query asks for more |
| `schemaCacheTtlSeconds` | number | How long a table's generated type stays cached before automatic rebuild |

Wildcards support `*` as "any run of characters." Denied tables/fields
never appear in introspection or query results, regardless of query shape.
