# Configuração

`custom/backoffice/graphql/config/graphql-config.json`:

| Chave | Tipo | Significado |
|---|---|---|
| `denyTables` | array de strings com curinga | Aliases de tabela nunca expostos, ex. `"SRH*"` |
| `denyFields` | array de strings com curinga | Nomes de campo nunca expostos, ex. `"*SENHA*"` |
| `allowMutations` | array de aliases de tabela (sem curinga) | Tabelas que aceitam mutations `createTABLE`/`updateTABLE`/`deleteTABLE`; vazio por padrão (todas as tabelas somente leitura) |
| `pagination.defaultPageSize` | número | `limit` usado quando a consulta o omite |
| `pagination.maxPageSize` | número | Teto rígido de `limit`, mesmo que a consulta peça mais |
| `schemaCacheTtlSeconds` | número | Tempo que o tipo gerado de uma tabela fica em cache antes de ser reconstruído automaticamente |

Os curingas suportam `*` como "qualquer sequência de caracteres" (aplica-se
apenas a `denyTables` e `denyFields`; `allowMutations` usa aliases exatos de
tabela). Tabelas/campos bloqueados nunca aparecem em introspecção nem em
resultados de consulta, independentemente da forma da query. Uma tabela
exige **ambos** o registro em `allowMutations` **e** ausência de
`denyTables` para ser gravável — as duas condições se combinam.