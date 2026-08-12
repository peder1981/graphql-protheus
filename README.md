# GraphQL Protheus — Motor GraphQL Nativo para TOTVS Protheus 12

Implementacao de um motor GraphQL completo, embarcado no appserver do Protheus 12.1.2510, desenvolvido inteiramente em TLPP.

> **Self-Service:** Adicione novas tabelas editando o `appserver.ini` — sem recompilar, sem tocar em TLPP.
> **Playground:** Explore e teste queries em `http://servidor:porta/graphql/playground`

## Visao Geral

Este projeto implementa o spec GraphQL (parse, validacao, execucao) de forma nativa em TLPP, sem dependencias externas (Node.js, Python, etc.). O motor é exposto via endpoint REST no proprio appserver.

### Principais funcionalidades

- Queries GraphQL completas (`find*` e `list*`) com paginacao e filtros
- Configuracao via `appserver.ini` — adiciona tabelas sem recompilar
- Auto-discovery de campos via dicionario SX3 do Protheus
- Playground interativo auto-contido (sem CDN externo)
- Documentacao completa e auto-generated

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
     ├── GqlConfig       ← parse appserver.ini [GraphQL]
     ├── GqlAutoDiscover ← discovery via SX3/SX1
     ├── GqlParser       → AST da query
     ├── GqlValidator    → validacao contra schema
     └── GqlExecutor     → execucao dos resolvers
              │
              ▼
         FWExecStatement (queries parametrizadas)
              │
              ▼
         Tabelas Protheus (SA1, SB1, SC5, ...)
```

## Endpoints Disponiveis

| Endpoint | Descricao |
|----------|-----------|
| `GET /graphql` | Endpoint principal de queries GraphQL |
| `GET /graphql/playground` | Interface interativa para testar queries |
| `GET /graphql/schema` | Schema completo em JSON (introspecao) |
| `GET /graphql/modules` | Lista de modulos configurados e status |

## Modulos Disponiveis

| Modulo | Tabela | Type GraphQL | Campos |
|--------|--------|-------------|--------|
| customer | SA1 | `Cliente` | codigo, nome, endereco, bairro, cidade, estado, telefone, tipo, inscricaoEstadual, cgc |
| product | SB1 | `Produto` | codigo, descricao, validade, unidademedida, codigobarras, localizacao |
| invoice | SC5 | `NotaFiscal` | numero, emissao, serie, cliente, serieCF |

## Configuracao Rapida (3 passos)

### Passo 1 — Adicione no `appserver.ini`

```ini
[REST]
/graphql = custom.backoffice.graphql.service.entrypoint
/graphql/playground = custom.backoffice.graphql.playground.entrypoint
/graphql/schema = custom.backoffice.graphql.schema.render
/graphql/modules = custom.backoffice.graphql.modules.render

[GraphQL]
default.first     = 10
default.maxFirst  = 100
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO,A1_TIPO
module.customer.enabled    = 1
module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA,B1_LOCPAD
module.product.filter      = B1_DESC
module.product.enabled     = 1
module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE,C5_SERIECF
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1
module.autoDiscover.enabled      = 0
```

### Passo 2 — Reinicie o appserver

```bash
net stop "TOTVS Application Server"
net start "TOTVS Application Server"
```

### Passo 3 — Teste

```bash
# Query direta
curl "http://servidor:porta/rest/graphql?query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7B%20codigo%20nome%20%7D%20%7D"

# Playground
open http://servidor:porta/graphql/playground

# Ver modulos
curl "http://servidor:porta/graphql/modules"
```

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
```graphql
{
  __type(name: "Cliente") {
    name
    fields { name }
  }
}
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
│   ├── executive.tlpp       # Orquestrador principal (GqlExecutive)
│   ├── config.tlpp          # Parse de appserver.ini (GqlConfig)
│   └── autodiscover.tlpp    # Discovery via SX3 (GqlAutoDiscover)
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
├── playground.tlpp          # Interface interativa HTML
├── playground.entrypoint.tlpp # Entry point REST /graphql/playground
├── schema.render.tlpp       # Entry point REST /graphql/schema
└── modules.render.tlpp      # Entry point REST /graphql/modules
```

## Documentacao

| Documento | Descricao |
|-----------|-----------|
| `docs/api-reference.md` | Referencia completa da API (tipos, operacoes, exemplos) |
| `docs/configuration.md` | Guia de configuracao INI (todas as chaves, exemplos dev/homolog/prod) |
| `docs/architecture.md` | Arquitetura do sistema (C4, fluxos, ADRs) |
| `docs/self-service-guide.md` | Guia do consumidor (primeira query, FAQ, troubleshooting) |
| `docs/changelog.md` | Historico de versoes |

## Limitacoes e Consideracoes

- **Parsing:** O parser implementa o subset mais comum do GraphQL (queries, campos, argumentos, variaveis, filtros). Nao suporta ainda: mutations, subscriptions, fragments, directives (`@skip`, `@include`), `@defer`/`@stream`.
- **Tipos:** Todos os campos sao mapeados como `String` por padrao. Tipos `Int`, `Float`, `Boolean`, `Date` requerem extendacao manual do schema.
- **Performance:** Cada resolver executa uma query SQL independente. Para cenarios com deep nesting, considere implementar DataLoader pattern.
- **Seguranca:** Queries sao parametrizadas via `FWExecStatement` (sem insetao SQL). Rate limiting e complexidade maxima de query devem ser implementados em camada de gateway (nginx/API Gateway).
- **Encoding:** O motor opera em UTF-8. A conversao de/para CP-1252 e feita automaticamente pelo framework REST do Protheus.
