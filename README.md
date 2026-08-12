# GraphQL Protheus — Motor GraphQL Nativo para TOTVS Protheus 12

Implementacao de um motor GraphQL completo, embarcado no appserver do Protheus 12.1.2510, desenvolvido inteiramente em TLPP.

## Visao Geral

Este projeto implementa o spec GraphQL (parse, validacao, execucao) de forma nativa em TLPP, sem dependencias externas (Node.js, Python, etc.). O motor é exposto via endpoint REST no proprio appserver.

## Arquitetura

```
Cliente GraphQL
     │
     │  GET /graphql?query={...}
     ▼
custom.backoffice.graphql.service.entrypoint (Entry Point REST)
     │
     ▼
GqlExecutive (orquestacao)
     ├── GqlParser    → AST da query
     ├── GqlValidator → validacao contra schema
     └── GqlExecutor  → execucao dos resolvers
              │
              ▼
         FWExecStatement (queries parametrizadas)
              │
              ▼
         Tabelas Protheus (SA1, SB1, SC5, ...)
```

## Modulos Disponiveis

| Modulo | Tabela | Type GraphQL | Campos |
|--------|--------|-------------|--------|
| customer | SA1 | `Cliente` | codigo, nome, endereco, bairro, cidade, estado, telefone, tipo, inscricaoEstadual, cgc |
| product | SB1 | `Produto` | codigo, descricao, validade, unidademedida, codigobarras, localizacao |
| invoice | SC5 | `NotaFiscal` | numero, emissao, serie, cliente, serieCF |

## Configuracao

1. Copiar os arquivos `.tlpp` para o projeto Protheus
2. Adicionar ao `appserver.ini`:
   ```ini
   [REST]
   /graphql=custom.backoffice.graphql.service.entrypoint
   ```
3. Compilar todos os arquivos TLPP na ordem correta
4. Reiniciar o appserver

## Uso

### Consulta Simples
```graphql
{
  findCliente(codigo: "000001") {
    codigo
    nome
    cidade
    estado
  }
}
```

### Lista com Paginacao
```graphql
{
  listCliente(primeiro: 10, offset: 0, cidade: "SAO PAULO") {
    codigo
    nome
    telefone
  }
}
```

### Produto
```graphql
{
  findProduto(codigo: "P001") {
    codigo
    descricao
    unidademedida
  }
}
```

### Introspeccao
```
GET /graphql
→ Retorna o schema completo em JSON
```

## Registro de Modulos Dinamicos

Para registrar novas tabelas em tempo de execucao:

```tlpp
local oExec := custom.backoffice.graphql.GqlExecutive():new()
oExec:registerModule("SD1", "ItemNotaFiscal", {"D1_NUM", "D1_ITEM", "D1_PRODUTO", "D1_QUANTID", "D1_PRECO"})
local cResult := oExec:executeQuery("{ listItemNotaFiscal(codigo: \"NF001\") { codigo descricao quantidade } }")
```

## Testes

Executar com TIR:
```bash
pytest tests/tir/test_graphql_sa1.tir -v
pytest tests/tir/test_graphql_sb1.tir -v
```

## Estrutura de Arquivos

```
custom/backoffice/graphql/
├── core/
│   ├── types.tlpp           # Tipos base (GqlScalarType, GqlField, GqlObjectType, GqlError)
│   ├── schema.tlpp          # Registry de tipos (GqlSchema)
│   ├── parser.tlpp          # Lexer + Parser GraphQL
│   ├── validator.tlpp       # Validador de queries
│   ├── executor.tlpp        # Executor de queries
│   └── executive.tlpp       # Orquestrador principal (GqlExecutive)
├── schema/
│   ├── customer.types.tlpp  # Type definitions SA1 (Cliente)
│   ├── product.types.tlpp   # Type definitions SB1 (Produto)
│   └── invoice.types.tlpp   # Type definitions SC5 (NotaFiscal)
├── resolvers/
│   ├── customer.init.tlpp   # Init resolvers SA1
│   ├── product.init.tlpp    # Init resolvers SB1
│   ├── invoice.init.tlpp    # Init resolvers SC5
│   └── generic.tlpp         # Generic resolver (SX3-driven)
├── service.entrypoint.tlpp  # Entry point REST /graphql
└── config/
    └── appserver-graphql.ini # Configuracao appserver
```

## Limitacoes e Consideracoes

- **Parsing:** O parser implementa o subset mais comum do GraphQL (queries, campos, argumentos, variaveis, filtros). Nao suporta ainda: mutations, subscriptions, fragments, directives (`@skip`, `@include`), `@defer`/`@stream`.
- **Tipos:** Todos os campos sao mapeados como `String` por padrao. Tipos `Int`, `Float`, `Boolean`, `Date` requerem extendacao manual do schema.
- **Performance:** Cada resolver executa uma query SQL independente. Para cenarios com deep nesting, considere implementar DataLoader pattern.
- **Seguranca:** Queries sao parametrizadas via `FWExecStatement` (sem insetao SQL). Rate limiting e complexidade maxima de query devem ser implementados em camada de gateway (nginx/API Gateway).
- **Encoding:** O motor opera em UTF-8. A conversao de/para CP-1252 e feita automaticamente pelo framework REST do Protheus.
