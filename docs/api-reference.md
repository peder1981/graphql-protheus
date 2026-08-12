# GraphQL Protheus — Referencia Completa da API

> Engine GraphQL nativa em TLPP para TOTVS Protheus 12.1.2510.
> Sem dependencias de Node.js — funciona diretamente no appserver Protheus.

---

## Visao Geral

A API expoe tabelas do Protheus como tipos GraphQL, com consultas (`find` e `list`) geradas automaticamente.
Cada modulo corresponde a uma tabela Protheus (SA1, SB1, SC5, etc.) e e mapeado para um tipo GraphQL
com campos em camelCase derivados dos campos da tabela (A1_COD → `codigo`, B1_DESC → `descricao`).

**Arquitetura:**

- Parser GraphQL recursive-descent em TLPP
- Validador de schema propio
- Executor que roda codeblocks resolver
- Motor CRUD sobre SQL via `FWExecStatement` e `TCQuery`
- Config via `appserver.ini` (secao `[GraphQL]`)
- Discovery automatico de tabelas via dicionario SX3

---

## Endpoints

### `GET /graphql`

Executa queries GraphQL e retorna JSON.

| Parametro | Obrigatorio | Tipo | Descricao |
|-----------|-------------|------|-----------|
| `query` | Sim | String | Query GraphQL formatada (URL-encoded) |
| `filial` | Nao | String | Filial para consulta. Se omitido, usa `MV_GQLFIL` |

**Cabecalho de resposta:**

```
Content-Type: application/json
```

**Exemplo de URL:**

```
/rest/graphql?query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7B%20codigo%20nome%20cidade%20%7D%20%7D
```

---

## Schema GraphQL

### Tipos Disponiveis

#### Cliente (SA1)

Tabela Protheus: `SA1` — Clientes / Fornecedores

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo GraphQL | Descricao |
|---------------|---------------|-------------|-----------|
| `codigo` | `A1_COD` | `String` | Codigo unico do cliente |
| `nome` | `A1_NOME` | `String` | Razao social / nome do cliente |
| `endereco` | `A1_END` | `String` | Endereco |
| `bairro` | `A1_BAIRRO` | `String` | Bairro |
| `cidade` | `A1_CIDADE` | `String` | Cidade |
| `estado` | `A1_ESTADO` | `String` | Sigla do estado |
| `telefone` | `A1_FONE` | `String` | Telefone |
| `tipo` | `A1_TIPO` | `String` | Tipo: `F`=Fisico, `J`=Juridico |
| `inscricaoEstadual` | `A1_INSCRM` | `String` | Inscricao estadual |
| `cgc` | `A1_CGC` | `String` | CGC/CPF |

Operacoes:

- `findCliente(codigo: String!): Cliente` — busca por codigo unico
- `listClientes(primeiro: Int, offset: Int, cidade: String, estado: String, tipo: String): [Cliente]` — lista com paginacao e filtros

**Observacoes:**
- Ordenacao padrao: `ORDER BY A1_NOME`
- Todos os filtros usam `LIKE` exceto `estado` e `tipo` que usam `=` exato
- Filtro `cidade` faz `LIKE '%valor%'` (busca parcial)

---

#### Produto (SB1)

Tabela Protheus: `SB1` — Produtos

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo GraphQL | Descricao |
|---------------|---------------|-------------|-----------|
| `codigo` | `B1_COD` | `String` | Codigo unico do produto |
| `descricao` | `B1_DESC` | `String` | Descricao do produto |
| `validade` | `B1_VALID` | `String` | Data de validade (formato `YYYY-MM-DD`) |
| `unidademedida` | `B1_UM` | `String` | Unidade de medida |
| `codigobarras` | `B1_CODBARRA` | `String` | Codigo de barras |
| `localizacao` | `B1_LOCPAD` | `String` | Localizacao padrao no estoque |

Operacoes:

- `findProduto(codigo: String!): Produto` — busca por codigo unico
- `listProdutos(palavra: String, primeiro: Int, offset: Int): [Produto]` — lista com busca por descricao e paginacao

**Observacoes:**
- Ordenacao padrao: `ORDER BY B1_DESC`
- Filtro `palavra` faz `LIKE '%valor%'` em `B1_DESC`
- Paginacao via `SKIP/FIRST` no SQL
- **Retorno envolto:** `{ "produtos": [...] }`

---

#### NotaFiscal (SC5)

Tabela Protheus: `SC5` — Notas Fiscais / Pedidos de Venda

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo GraphQL | Descricao |
|---------------|---------------|-------------|-----------|
| `numero` | `C5_NUM` | `String` | Numero da nota fiscal |
| `emissao` | `C5_EMISSAO` | `String` | Data de emissao (formato `YYYY-MM-DD`) |
| `serie` | `C5_SERIE` | `String` | Serie da nota |
| `cliente` | `C5_CLIENTE` | `String` | Codigo do cliente |
| `serieCF` | `C5_SERIECF` | `String` | Serie do documento fiscal (CF) |

Operacoes:

- `findNotaFiscal(numero: String!, serie: String!): NotaFiscal` — busca por numero e serie
- `listNotasFiscais(cliente: String, dataIni: String, dataFim: String, primeiro: Int, offset: Int): [NotaFiscal]` — lista com filtros e paginacao

**Observacoes:**
- Ordenacao padrao: `ORDER BY C5_EMISSAO DESC`
- Filtro `cliente` usa `=` exato
- Filtros de data `dataIni`/`dataFim` usam `>=` e `<=` (formato `YYYY-MM-DD`)
- Paginacao via `SKIP/FIRST` no SQL
- **Retorno envolto:** `{ "notasFiscais": [...] }`

---

## Mapeamento de Campos Protheus → GraphQL

A engine converte automaticamente nomes de campos Protheus (caixa alta com underscore)
para camelCase GraphQL:

| Campo Protheus | Campo GraphQL | Tipo Protheus | Tipo GraphQL | Nota |
|---------------|---------------|--------------|-------------|------|
| `A1_COD` | `codigo` | C | String | Chave primaria SA1 |
| `A1_NOME` | `nome` | C | String | |
| `A1_END` | `endereco` | C | String | |
| `A1_BAIRRO` | `bairro` | C | String | |
| `A1_CIDADE` | `cidade` | C | String | Filtros LIKE |
| `A1_ESTADO` | `estado` | C | String | Filtros = |
| `A1_FONE` | `telefone` | C | String | |
| `A1_TIPO` | `tipo` | C | String | Filtros = (F/J) |
| `A1_INSCRM` | `inscricaoEstadual` | C | String | |
| `A1_CGC` | `cgc` | C | String | |
| `B1_COD` | `codigo` | C | String | Chave primaria SB1 |
| `B1_DESC` | `descricao` | C | String | Filtro LIKE |
| `B1_VALID` | `validade` | D | String | Data → YYYY-MM-DD |
| `B1_UM` | `unidademedida` | C | String | |
| `B1_CODBARRA` | `codigobarras` | C | String | |
| `B1_LOCPAD` | `localizacao` | C | String | |
| `C5_NUM` | `numero` | C | String | Chave parcial SC5 |
| `C5_EMISSAO` | `emissao` | D | String | Data → YYYY-MM-DD |
| `C5_SERIE` | `serie` | C | String | Chave parcial SC5 |
| `C5_CLIENTE` | `cliente` | C | String | Filtro = |
| `C5_SERIECF` | `serieCF` | C | String | |

> **Nota:** Campos do tipo data (`D`) sao retornados como strings no formato `YYYY-MM-DD` via `dValToChar()`.

---

## Exemplos de Query

### Consulta Simples — Encontrar Cliente

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

**Retorno:**

```json
{
  "data": {
    "findCliente": {
      "codigo": "000001",
      "nome": "Empresa Exemplo LTDA",
      "cidade": "SAO PAULO",
      "estado": "SP"
    }
  }
}
```

---

### Lista com Paginacao

```graphql
{
  listClientes(primeiro: 10, offset: 0) {
    codigo
    nome
  }
}
```

**Retorno:**

```json
{
  "data": {
    "listClientes": [
      { "codigo": "000001", "nome": "Empresa A" },
      { "codigo": "000002", "nome": "Empresa B" }
    ]
  }
}
```

---

### Lista com Filtros

```graphql
{
  listClientes(primeiro: 5, offset: 0, cidade: "SAO PAULO", tipo: "J") {
    codigo
    nome
    cidade
    tipo
  }
}
```

---

### Produto

```graphql
{
  findProduto(codigo: "P001") {
    codigo
    descricao
    unidademedida
    validade
  }
}
```

**Retorno:**

```json
{
  "data": {
    "findProduto": {
      "produto": {
        "codigo": "P001",
        "descricao": "Parafuso六角 1/4 x 20",
        "unidademedida": "UN",
        "validade": ""
      }
    }
  }
}
```

---

### Nota Fiscal

```graphql
{
  findNotaFiscal(numero: "12345", serie: "1") {
    numero
    emissao
    serie
    cliente
  }
}
```

**Retorno:**

```json
{
  "data": {
    "findNotaFiscal": {
      "notaFiscal": {
        "numero": "12345",
        "emissao": "2024-01-15",
        "serie": "1",
        "cliente": "000001"
      }
    }
  }
}
```

---

### Lista de Notas Fiscais com Filtro de Data

```graphql
{
  listNotasFiscais(primeiro: 20, offset: 0, cliente: "000001", dataIni: "2024-01-01", dataFim: "2024-12-31") {
    numero
    emissao
    serie
    cliente
  }
}
```

**Retorno:**

```json
{
  "data": {
    "listNotasFiscais": {
      "notasFiscais": [
        {
          "numero": "12345",
          "emissao": "2024-06-15",
          "serie": "1",
          "cliente": "000001"
        }
      ]
    }
  }
}
```

---

### Introspeccao — Tipos Disponiveis

```graphql
{
  __schema {
    queryType { name }
    types { name }
  }
}
```

---

### Introspeccao — Campos de um Tipo

```graphql
{
  __type(name: "Cliente") {
    name
    fields {
      name
      description
    }
  }
}
```

---

## Parametros de Query

| Parametro | Obrigatorio | Descricao | Exemplo |
|-----------|-------------|-----------|---------|
| `query` | Sim | Query GraphQL formatada | `query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7B%20codigo%20%7D%20%7D` |
| `filial` | Nao | Filial para consulta. Usa `MV_GQLFIL` se omitido | `filial=01` |

---

## Parametros de Paginacao

| Parametro | Padrao | Maximo | Descricao |
|-----------|--------|--------|-----------|
| `primeiro` | 10 | 100 | Quantidade maxima de registros a retornar |
| `offset` | 0 | — | Numero de registros a pular (paginacao ordinal) |

> **Nota:** A paginação é aplicada de formas diferentes por modulo:
> - SA1: filtro pos-query com contador
> - SB1/SC5: `SKIP/FIRST` nativo no SQL

---

## Tratamento de Erros

Erros sao retornados no padrao GraphQL official com array `errors`:

```json
{
  "errors": [
    {
      "message": "Unknown field 'nomeFantasia' on type 'Cliente'",
      "extensions": {
        "code": "VALIDATION_ERROR"
      }
    }
  ]
}
```

| Codigo | Significado | Causa Comum |
|--------|------------|-------------|
| `PARSE_ERROR` | Query GraphQL com sintaxe invalida | Chaves desbalanceadas, falta dois pontos em argumentos |
| `VALIDATION_ERROR` | Campo inexistente no schema | Nome de campo errado, tipo inexistente |
| `EXECUTION_ERROR` | Erro durante execucao | Tabela nao encontrada, problema de conexao |

**Exemplo de erro de validacao:**

```json
{
  "data": null,
  "errors": [
    {
      "message": "Unknown field 'nomeFantasia' on type 'Cliente'",
      "extensions": { "code": "VALIDATION_ERROR" }
    }
  ]
}
```

**Exemplo de erro de parse:**

```json
{
  "errors": [
    { "message": "Expected name but found ''" }
  ]
}
```

---

## Como Adicionar um Novo Modulo (Tabela)

### Via Código (Entrypoint)

No entrypoint (`service.entrypoint.tlpp`), adicione uma chamada `registerModule` antes da execucao:

```tlpp
oExecutive:registerModule("SXX", "MeuTipo", {"X9_COD", "X9_DESC", "X9_TIPO"})
```

O modulo sera registrado automaticamente com campos em camelCase, queries `findMeuTipo` e `listMeuTipo`.

### Via Configuracao INI (Auto-Discovery)

Para habilitar discovery automatico de todas as tabelas do dicionario:

```ini
[GraphQL]
module.autoDiscover.enabled    = 1
module.autoDiscover.minFields  = 3
module.autoDiscover.skipTables = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
```

### Configuracao Completa do appserver.ini

```ini
; ---- REST ----
[REST]
/graphql=custom.backoffice.graphql.service.entrypoint

; ---- GraphQL Engine ----
[GraphQL]
default.first    = 10
default.maxFirst = 100
default.offset   = 0
log.enabled      = 0
log.level        = INFO

; Auto-discovery de tabelas
module.autoDiscover.enabled    = 1
module.autoDiscover.minFields  = 3
module.autoDiscover.skipTables = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
```

> **Nota:** Nenhum recompilacao e necessaria para alteracoes de configuracao INI — o modulo e reloadado automaticamente no proximo request.

---

## Estrutura de Diretorio

```
custom/backoffice/graphql/
├── service.entrypoint.tlpp   # Entry point U_GQLSERVICE (GET /graphql)
├── playground.tlpp           # Interface interativa HTML
├── core/
│   ├── types.tlpp            # GqlScalarType, GqlField, GqlObjectType, GqlQueryType, GqlError
│   ├── schema.tlpp           # GqlSchema — registry de tipos
│   ├── parser.tlpp           # GqlParser — recursive-descent parser GraphQL
│   ├── validator.tlpp        # GqlValidator — validacao contra schema
│   ├── executor.tlpp         # GqlExecutor — execucao de queries
│   ├── executive.tlpp        # GqlExecutive — orquestracao principal
│   ├── config.tlpp           # GqlConfig — leitura de appserver.ini
│   └── autodiscover.tlpp     # GqlAutoDiscover — discovery via SX3
├── schema/
│   ├── customer.types.tlpp   # Tipo Cliente + queries SA1
│   ├── product.types.tlpp    # Tipo Produto + queries SB1
│   └── invoice.types.tlpp    # Tipo NotaFiscal + queries SC5
├── resolvers/
│   ├── customer.init.tlpp    # initSA1Schema()
│   ├── product.init.tlpp     # initSB1Schema()
│   ├── invoice.init.tlpp     # initSC5Schema()
│   └── generic.tlpp          # GqlGenericResolver (resolutor generico)
└── config/
    └── appserver-graphql.ini # Snippet para appserver.ini
```

---

## Notas Técnicas

### Filial

Todas as consultas incluem automaticamente:
- Filtro `D_E_L_E_T_ = ' '` (registros nao deletados)
- Filtro `TABLE_FILIAL = '<filial>'` (isolamento por filial)
- Hint `%nolock%` (sem locks de leitura)

### Performance

- Queries usam `FWExecStatement` para SQL embedded (previne SQL injection)
- Queries SB1/SC5 usam `TCQuery` para paginacao eficiente com `SKIP/FIRST`
- Default de paginacao: 10 registros, maximo 100

### Codificacao

- Todos os fontes em **CP-1252 (Windows-1252)**
- Sem BOM
- Includes: `tlpp-core.th` (primeiro), `totvs.ch` (segundo)

### Respostas Envoltas (Wrapped Responses)

| Modulo | find retorna | list retorna |
|--------|-------------|-------------|
| SA1 (Cliente) | Objeto direto | Array direto |
| SB1 (Produto) | `{ "produto": {...} }` | `{ "produtos": [...] }` |
| SC5 (NotaFiscal) | `{ "notaFiscal": {...} }` | `{ "notasFiscais": [...] }` |
