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

The permission hook (`GqlAccessControl:allowField`) always returns `.T.`
in this sub-project — it exists so the Auth sub-project can wire in real
per-user permissions without touching any other file.
