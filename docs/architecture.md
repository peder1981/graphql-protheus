# GraphQL Protheus — Documentacao de Arquitetura

**Versao:** 2.0.0
**Data:** 2026-08-11
**Autor:** GraphQL Engine Team

---

## 1. Visao Geral

O GraphQL Protheus e um motor GraphQL nativo implementado inteiramente em TLPP (TOTVS Language Plus Plus), executado diretamente dentro do appserver TOTVS Protheus 12.1.2510. Seu objetivo e expor as tabelas do ERP como tipos GraphQL consultaveis via HTTP, permitindo que consumidores (frontends, microservicos, scripts) recuperem dados do Protheus sem necessidade de camada intermediaria Node.js, Python ou qualquer tecnologia externa.

### Por que este projeto existe

Sistemas ERP como o TOTVS Protheus tradicionalmente expoe seus dados apenas por meio de telas SmartClient ou APIs REST customizadas, cada uma com seu proprio formato e contratos. O GraphQL Protheus resolve tres problemas:

1. **Unificacao de acesso** — diferentes tabelas (SA1, SB1, SC5, etc.) sao expostas via um unico endpoint padrao com schema tipado.
2. **Self-service** — consumidores podem descobrir tipos, campos e filtros sem precisar consultar um especialista Protheus.
3. **Configuracao declarativa** — novas tabelas sao adicionadas editando o `appserver.ini`, sem recompilar o codigo TLPP.

### Principios arquiteturais

- **Zero dependencias externas** — tudo roda no appserver; nenhum servidor Node.js, Nginx reverso ou banco separado.
- **Code-first** — o schema e construido programaticamente via classes TLPP, nao via arquivo SDL (.graphql).
- **Configuracao por INI** — comportamento controlado por chaves no appserver.ini, nao por hardcoded.
- **Auto-discovery** — campos de tabelas sao obtidos automaticamente do dicionario SX3 do Protheus.
- **Seguranca por padrao** — todas as queries usam `FWExecStatement` (parametrizacao), filtro de soft-delete (`D_E_L_E_T_ = ' '`) e isolamento por filial.

---

## 2. C4 Level 1 — Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    ECOSSETO PROTHEUS                               │
│                                                                                     │
│   ┌──────────────┐      ┌──────────────────────────────────────────────────────┐    │
│   │  Consumidores  │      │              PROTHEUS APPSERVER 12                   │    │
│   │              │      │                                                      │    │
│   │  • Frontend  │─────▶│  ┌──────────────────────────────────────────────┐    │    │
│   │  • Mobile    │      │  │              REST Layer                      │    │    │
│   │  • Script    │─────▶│  │  /graphql          → service.entrypoint      │    │    │
│   │  • BI/Etl    │─────▶│  │  /graphql/playground → playground.entrypoint │    │    │
│   │  • Outros    │─────▶│  │  /graphql/schema   → schema.render           │    │    │
│   │              │─────▶│  │  /graphql/modules  → modules.render          │    │    │
│   └──────────────┘      │  └──────────────────────────────────────────────┘    │    │
│                         │                                                      │    │
│                         │  ┌──────────────────────────────────────────────┐    │    │
│                         │  │         GraphQL Engine (TLPP puro)            │    │    │
│                         │  │                                              │    │    │
│                         │  │  GqlParser  →  GqlValidator  →  GqlExecutor  │    │    │
│                         │  │       │              │               │       │    │    │
│                         │  │       ▼              ▼               ▼       │    │    │
│                         │  │  GqlConfig  ←  GqlExecutive  →  GqlSchema   │    │    │
│                         │  │                    │                         │    │    │
│                         │  │              GqlAutoDiscover                 │    │    │
│                         │  │                    │                         │    │    │
│                         │  └────────────────────┼────────────────────────┘    │    │
│                         │                                                      │    │
│                         │  ┌──────────────────────────────────────────────┐    │    │
│                         │  │               Dicionario Protheus             │    │    │
│                         │  │  SA1 ─┐   SB1 ─┐   SC5 ─┐   SX1 ─┐  SX3 ─┐ │    │    │
│                         │  │  SB2 ─┤   SD1 ─┤        SX2 ─┘  SX6 ─┘     │    │    │
│                         │  └──────────────────────────────────────────────┘    │    │
│                         └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Descricao dos componentes:**

| Componente | Responsabilidade |
|---|---|
| **Consumidores** | Qualquer cliente HTTP que envie queries GraphQL — navegadores (playground), scripts Python, dashboards, etc. |
| **REST Layer** | Mapeia URLs do appserver para os entry points TLPP correspondentes, definido no `appserver.ini` secao `[REST]` |
| **GqlParser** | Parse recursive-descent da query GraphQL → AST (Abstract Syntax Tree) em JSON |
| **GqlValidator** | Valida o AST contra o schema registrado no `GqlSchema` |
| **GqlExecutor** | Executa o AST, invocando os resolvers registrados e retornando JSON |
| **GqlExecutive** | Orquestrador principal: instancia o schema, carrega configuracao, registra modulos |
| **GqlConfig** | Le a secao `[GraphQL]` do `appserver.ini` e expoe as configuracoes como metodo de classe |
| **GqlAutoDiscover** | Consulta o dicionario SX3/SX1 do Protheus para descobrir campos de tabelas automaticamente |
| **GqlSchema** | Registro de tipos GraphQL — cada modulo registrado adiciona um `GqlObjectType` + queries `find*` e `list*` |
| **Dicionario Protheus** | Tabelas SX1 (tabelas), SX2 (campos de tabelas genericas), SX3 (campos padrao), SX6 (parametros) |

---

## 3. C4 Level 2 — Container Diagram

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                    PROTHEUS APPSERVER 12.1.2510                                   │
│                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        HTTP Request Handler                                 │  │
│  │                                                                              │  │
│  │  Appserver receives GET /graphql?query=...                                  │  │
│  │       │                                                                      │  │
│  │       ▼                                                                      │  │
│  │  custom.backoffice.graphql.service.entrypoint (TLPP)                        │  │
│  │       │                                                                      │  │
│  │       ▼                                                                      │  │
│  │  U_GQLSERVICE() → cria GqlExecutive, chama executeQuery()                   │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                             │
│                                      ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        GraphQL Core Engine                                   │  │
│  │                                                                              │  │
│  │  GqlExecutive                                                               │  │
│  │   ├── GqlConfig (config.tlpp)         ← leitura de appserver.ini             │  │
│  │   ├── GqlAutoDiscover (autodiscover.tlpp) ← consulta SX3/SX1                │  │
│  │   │                                                                     │  │
│  │   ├── GqlSchema (schema.tlpp)         ← registry de tipos                  │  │
│  │   │   └── GqlObjectType + GqlField + GqlScalarType                        │  │
│  │   │                                                                     │  │
│  │   ├── GqlParser (parser.tlpp)         ← recursive-descent parser            │  │
│  │   │   └── GqlLexer → tokens → AST (json)                                 │  │
│  │   │                                                                     │  │
│  │   ├── GqlValidator (validator.tlpp)   ← validacao contra schema            │  │
│  │   │   └── checa tipos, campos, argumentos                                 │  │
│  │   │                                                                     │  │
│  │   └── GqlExecutor (executor.tlpp)     ← execucao dos resolvers             │  │
│  │       └── resolve campo por campo, chama resolvers do schema              │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                             │
│                                      ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        Resolvers                                             │  │
│  │                                                                              │  │
│  │  resolveList()  ← gera SQL com FWExecStatement, aplica paginacao            │  │
│  │  resolveFind()  ← gera SQL de busca por chave primaria                      │  │
│  │  toCamelCase()  ← converte A1_COD → a1Cod                                   │  │
│  │                                                                              │  │
│  │  Resolvers por modulo (schema/) + generic (resolvers/generic.tlpp)          │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                      │                                             │
│                                      ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        Dados Protheus                                        │  │
│  │                                                                              │  │
│  │  SA1 (Clientes)   SB1 (Produtos)   SC5 (Notas Fiscais)   + tabelas           │  │
│  │  via FWExecStatement / TCQuery                                            │  │
│  │  + Dicionario: SX1 (tabelas) / SX3 (campos)                                │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        Playghround + Endpoints auxiliares                    │  │
│  │                                                                              │  │
│  │  /graphql/playground → playground.tlpp (GqlPlayground:render()) → HTML      │  │
│  │  /graphql/schema   → schema.render.tlpp (introspecao expandida JSON)        │  │
│  │  /graphql/modules  → modules.render.tlpp (GqlExecutive:getModuleMetadata()) │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Fluxo de Execucado de uma Query

A sequencia completa, do HTTP request ao JSON de resposta:

### Passo 1 — Requisicao HTTP

```
GET /rest/graphql?query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7D
```

O appserver Protheus identifica a URL `/rest/graphql` e redireciona para o entry point
definido no `appserver.ini` secao `[REST]`: `custom.backoffice.graphql.service.entrypoint`.

### Passo 2 — Entry Point

`service.entrypoint.tlpp` define a funcao `U_GQLSERVICE()`:

```tlpp
function U_GQLSERVICE()
    local oExec  := custom.backoffice.graphql.GqlExecutive():new()
    local cQuery := GetParam("query", "")
    local cFilial := GetParam("filial", "")
    local oResult := oExec:executeQuery(cQuery, cFilial)
    FWResponseJson(oResult)
return
```

A funcao:
1. Cria uma instancia de `GqlExecutive`
2. Extrai o parametro `query` (URL-decoded) e opcionalmente `filial`
3. Chama `executeQuery()`

### Passo 3 — GqlExecutive:executeQuery()

`executive.tlpp:132-163` — a implementacao real:

```
1. oDoc := oParser:parse(cQuery)
   → GqlParser constrroi o lexer, gera tokens, chama recursive-descent parser
   → retorna JSON representando o AST, ou nil em caso de erro

2. if oDoc == nil → retorna erro PARSE_ERROR
   → { "errors": [{"message": "Parse error...", "extensions": {"code": "PARSE_ERROR"}}] }

3. aParseErr := JsonGet(oDoc, "errors")
   → se houver erros de parse, retorna-os diretamente

4. Resolve filial: usa parametro da URL ou cDefaultFilial do executive
   → ::oExecutor:setFilial(cUsedFil)

5. oResult := oExecutor:execute(oDoc)
   → GqlExecutor percorre o AST, para cada campo:
     a. Busca o resolver registrado no GqlSchema
     b. Chama o codeblock do resolver com (parent, args, schema, filial)
     c. Para campos escalares, usa o resolver de campo (JsonGet no parent)
     d. Para objetos aninhados, recursao
```

### Passo 4 — GqlParser (recursive-descent)

```
GqlParser:parse(cQuery)
  → GqlLexer:tokenize(cQuery)     // quebra em tokens: {, }, :, (, ), ", Nome, ...
  → parseDocument(tokens)          // retorna { "operations": [...] }
      → parseOperationDefinition() // "query" opcional, nome opcional, selectionSet
          → parseSelectionSet()    // lista de selecoes entre { }
              → parseField()       // nome do campo + argumentos opcionais + subselecoes
```

Cada nodo do AST e representado como um objeto JSON:
```json
{
  "kind": "operation",
  "operationType": "query",
  "selections": [
    {
      "kind": "field",
      "name": "findCliente",
      "arguments": [
        { "name": "codigo", "value": { "kind": "string", "value": "000001" } }
      ],
      "selections": [
        { "kind": "field", "name": "codigo" },
        { "kind": "field", "name": "nome" }
      ]
    }
  ]
}
```

### Passo 5 — GqlValidator

```
GqlValidator:validate(oAst, oSchema)
  → para cada operacao no AST:
      → valida que o tipo de operacao (query) existe no schema
      → para cada campo na selecao:
          → valida que o campo existe no tipo Query
          → valida argumentos (nome e tipo)
          → se houver subselecoes, recursa no tipo de retorno
```

Erros de validacao incluem:
- `Unknown field 'X' on type 'Query'`
- `Unknown type 'NaoExiste'`
- `Field X required but not provided`

### Passo 6 — GqlExecutor (resolucao)

```
GqlExecutor:execute(oDoc)
  → para cada operacao:
      → para cada selecao no top-level (tipo Query):
          → busca o resolver no schema: oSchema:getQueryType():getField(campo)
          → chama o codeblock: bResolver(oParent=nil, oArgs=args, oSch=oSchema, cFil=cFilial)
          → para campos do objeto resultado:
              → bFieldResolver(parent, field, schema, filial)
              → para campos escalares: JsonGet(parent, campoGraphQL)
```

Para a query `findCliente(codigo: "000001")`:
```
1. Resolver de "findCliente" e invocado com args = {"codigo": "000001"}
2. resolveFind("SA1", ["A1_COD","A1_NOME",...], "a1Cod", args, "01")
3. SQL gerado:
   SELECT A1_COD, A1_NOME, ...
   FROM SA1
   WHERE D_E_L_E_T_ = ' '
     AND A1_COD = '000001'
4. Resultado: array com 1 registro → convertido para JSON
5. Retorna o objeto Cliente com os campos solicitados
```

Para a query `listClientes(primeiro: 10, offset: 0)`:
```
1. Resolver de "listClientes" e invocado com args = {"primeiro": 10, "offset": 0}
2. resolveList("SA1", ["A1_COD","A1_NOME",...], "a1Cod", args, "01")
3. SQL gerado:
   SELECT A1_COD, A1_NOME, ...
   FROM SA1
   WHERE D_E_L_E_T_ = ' '
   ORDER BY A1_COD
   TOP 10 SKIP 0
4. Resultado: array de 10 objetos Cliente
```

### Passo 7 — Resposta HTTP

```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": {
    "findCliente": {
      "a1Cod": "000001",
      "a1Nome": "Empresa Exemplo LTDA",
      "a1Cidade": "SAO PAULO"
    }
  }
}
```

Em caso de erro:
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

---

## 5. Fluxo de Configuracao (INI → GqlConfig → GqlExecutive)

### Visao geral

```
appserver.ini (secao [GraphQL])
        │
        │  GetIniKey("GraphQL", "module.customer.table", ...)
        │  GetIniKey("GraphQL", "module.customer.type", ...)
        │  GetIniKey("GraphQL", "default.first", ...)
        │  GetIniKey("GraphQL", "module.autoDiscover.enabled", ...)
        │
        ▼
   GqlConfig():new()
        │
        │  discoverModules() → varre chaves module.*.table
        │  Parse valores globais (first, maxFirst, offset, log)
        │  Parse auto-discovery (enabled, skipTables, minFields)
        │
        ▼
   GqlExecutive():new()
        │
        │  oConfig  := GqlConfig():new()
        │  oAutoDisc := GqlAutoDiscover():new(oConfig)
        │
        ▼
   oExecutive:loadFromConfig()
        │
        │  Para cada modulo descoberto:
        │    1. isModuleEnabled()? → senao, pula
        │    2. cTable + cTypeName existem? → senao, pula
        │    3. campos definidos manualmente? → sim: usa campos
        │    4. campos definidos manualmente? → nao: autoDiscover.getTableFields(cTable)
        │    5. campos descobertos >= minFields? → senao, pula
        │    6. registerModule(cTable, cTypeName, aFields)
        │       → cria GqlObjectType + campos + queries find* e list*
        │
        ▼
   Schema GraphQL pronto para consumo
```

### Mapeamento de chaves INI → metodos GqlConfig

| Chave INI | Metodo GqlConfig | Valor padrao |
|---|---|---|
| `default.first` | `getDefaultFirst()` | `10` |
| `default.maxFirst` | `getMaxFirst()` | `100` |
| `default.offset` | `getDefaultOffset()` | `0` |
| `log.enabled` | `isLogEnabled()` | `0` (.F.) |
| `log.level` | `getLogLevel()` | `"INFO"` |
| `module.autoDiscover.enabled` | `getAutoDiscoverEnabled()` | `0` (.F.) |
| `module.autoDiscover.skipTables` | `getAutoDiscoverSkipTables()` | `"SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL"` |
| `module.autoDiscover.minFields` | `getAutoDiscoverMinFields()` | `3` |
| `module.<nome>.table` | `getModuleField(nome, "table")` | `""` |
| `module.<nome>.type` | `getModuleField(nome, "type")` | `""` |
| `module.<nome>.fields` | `getModuleField(nome, "fields")` | `""` |
| `module.<nome>.filter` | `getModuleField(nome, "filter")` | `""` |
| `module.<nome>.enabled` | `isModuleEnabled(nome)` | `0` (.F.) |
| `module.<nome>.maxFirst` | `getModuleField(nome, "maxFirst")` | N/A |

### Descoberta de modulos

O metodo `discoverModules()` do `GqlConfig` (config.tlpp:102-148) funciona em duas fases:

1. **Scan de nomes comuns** — verifica as 10 chaves padrao (`module.customer.table`, `module.product.table`, etc.)
2. **Scan dinamico** — usa `GetIniSection("GraphQL", "")` para listar todas as chaves na secao `[GraphQL]`, identifica aquelas que seguem o padrao `module.<nome>.table`

Os modulos descobertos sao armazenados em `aModules` e retornados por `getModuleKeys()`.

---

## 6. Fluxo de Auto-Discovery (SX3 → GqlAutoDiscover)

### Visao geral

```
GqlAutoDiscover():new(oConfig)
        │
        │  cFilial := xFilial("SA1")  // filial padrao para consultas ao dicionario
        │
        ▼
discover()
        │
        │  1. Query SX1: listar todas as tabelas do banco
        │     SELECT SX1_TABELA FROM SX1 WHERE SX1_FILIAL='{fil}' AND SX1_TIPO in ('T','V')
        │
        │  2. Para cada tabela (exceto skipTables):
        │     │
        │     ▼
        │  getTableFieldsDirect(tabela)
        │     │
        │     │  Query SX3:
        │     │  SELECT ADQ_CAMPO FROM SX3
        │     │  WHERE SX3_FILIAL='{fil}' AND SX3_TABELA='{tabela}'
        │     │    AND ADQ_CAMPO != ''
        │     │    AND ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%'
        │     │    AND ADQ_CAMPO NOT LIKE 'XI%'
        │     │
        │     ▼
        │  Retorna array de nomes de campo
        │
        │  3. Filtro: len(aFields) >= minFields? → se nao, ignora
        │
        │  4. Popula cache: {"SA1": {fields:[...], count:N}, "SB1": {...}, ...}
        │
        ▼
getModuleMetadata() → endpoint /graphql/modules
```

### Critérios de filtragem do auto-discovery

Uma tabela e considerada para auto-discovery se:

| Condicao | Descricao | Motivo |
|---|---|---|
| `SX1_TIPO in ('T','V')` | Apenas tabelas e visoes, nao indexes nem triggers | Evitar ruido |
| Nao esta em `skipTables` | Exclui tabelas do dicionario (SX1, SX2, SX3, etc.) | Nao sao tabelas de negocio |
| `len(campos) >= minFields` | No minimo 3 campos (padrao) | Evita tabelas com poucos campos utiles |
| `ADQ_CAMPO != ''` | Campo nao pode ser vazio | Campos validos |
| `ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%'` | Exclui campo de soft-delete | Campo interno do Protheus |
| `ADQ_CAMPO NOT LIKE 'XI%'` | Exclui campos de index | Campo interno do Protheus |

### Exemplo de saida do auto-discovery

```json
{
  "SA1": {
    "fields": ["A1_COD", "A1_NOME", "A1_END", "A1_BAIRRO", "A1_CIDADE", "A1_ESTADO", ...],
    "count": 120
  },
  "SB1": {
    "fields": ["B1_COD", "B1_DESC", "B1_VALID", "B1_UM", "B1_CODBARRA", ...],
    "count": 85
  },
  "SC5": {
    "fields": ["C5_NUM", "C5_EMISSAO", "C5_SERIE", "C5_CLIENTE", ...],
    "count": 42
  }
}
```

---

## 7. Guia de Extensibilidade

### 7.1 Adicionar um novo modulo sem alterar codigo TLPP

**Passo 1** — Edite o `appserver.ini`:

```ini
[GraphQL]
module.<nome>.table   = SXX    // alias da tabela Protheus
module.<nome>.type    = MeuTipo  // nome do tipo GraphQL
module.<nome>.fields  = X9_COD,X9_DESC,X9_TIPO,X9_SITUACAO  // campos expostos
module.<nome>.filter  = X9_DESC,X9_TIPO                      // campos filtraveis
module.<nome>.enabled = 1                                    // habilita o modulo
```

**Passo 2** — Reinicie o appserver:

```bash
net stop "TOTVS Application Server"
net start "TOTVS Application Server"
```

**Passo 3** — Verifique o carregamento:

```bash
curl "http://servidor:porta/graphql/modules"
```

Ou verifique o log do appserver por:
```
GqlExecutive: loaded module '<nome>' (SXX) with N campos
```

**Passo 4** — Teste a query:

```graphql
{
  listMeuTipo(primeiro: 10, offset: 0) {
    x9Cod
    x9Desc
    x9Tipo
  }
}
```

### 7.2 Adicionar com auto-discovery (sem listar campos)

Se `module.<nome>.fields` estiver vazio e o auto-discovery estiver habilitado, os campos sao
obtidos automaticamente do dicionario SX3:

```ini
[GraphQL]
module.autoDiscover.enabled      = 1
module.autoDiscover.minFields    = 3

module.mytable.table   = SXX
module.mytable.type    = MeuTipo
module.mytable.fields  =            // vazio — usa auto-discovery
module.mytable.enabled = 1
```

### 7.3 Adicionar via codigo (TLPP)

Para registro dinamico em tempo de execucao (sem reiniciar o appserver):

```tlpp
local oExec := custom.backoffice.graphql.GqlExecutive():new()
oExec:registerModule("SD1", "ItemNotaFiscal", {"D1_NUM", "D1_ITEM", "D1_PRODUTO", "D1_QUANTID", "D1_PRECO"})
local cResult := oExec:executeQuery("{ listItemNotaFiscal(codigo: \"NF001\") { codigo descricao quantidade } }")
```

### 7.4 Adicionar um novo tipo com campos customizados (override)

Se voce precisar de campos calculados ou mapeamentos especiais, crie um novo resolver no arquivo
correspondente em `resolvers/`:

```tlpp
method resolveCustom(cTable as character, aFields as array, oArgs as json, cFilial as character) as array
    // implementacao customizada
endmethod
```

E registre no schema via `GqlExecutive:registerModule()` antes de executar queries.

### 7.5 Estrutura de arquivos para extensao

```
custom/backoffice/graphql/
├── core/
│   ├── config.tlpp        ← extend se precisar de novas chaves INI
│   └── autodiscover.tlpp  ← extend se precisar de novos filtros de tabela
├── schema/
│   └── (novos arquivos .tlpp por dominio, se necessario)
└── resolvers/
    └── (novos arquivos .tlpp por dominio, se necessario)
```

---

## 8. Architecture Decision Records (ADRs)

### ADR-001: GraphQL Nativo TLPP vs Camada Node.js

**Estado:** Aceito
**Contexto:** Em 2024, a opcao comum para expor dados Protheus como GraphQL era usar uma camada
Node.js (Apollo Server, GraphQL Yoga) que se conectava ao banco via ODBC. Isso exigiria:
- Servidor Node.js adicional
- Gerenciamento de dependencia (Node, NPM packages)
- Sessao de banco separada
- Deploy e monitoramento duplicados

**Decisao:** Implementar o motor GraphQL inteiramente em TLPP, rodando dentro do proprio appserver Protheus. Zero dependencias externas.

**Consequencias:**
- Vantagem: deployment mais simples (um unico servico), nenhuma nova infraestrutura
- Vantagem: acesso nativo a funcoes Protheus (`FWExecStatement`, `RetSqlName`, `xFilial`)
- Vantagem: nenhuma latencia de conexao externa
- Desvantagem: parser GraphQL e validacao sao implementacoes proprieiras (subset limitado)
- Desvantagem: nao ha ecosistema de plugins GraphQL como em Node.js
- Desvantagem: complexidade maxima de query deve ser controlada na camada de gateway (nginx/API Gateway)

**Alternativas consideradas:**
- Apollo Server + SQL adapter: rejeitado por adicionar dependencia de infraestrutura
- Hasura sobre Protheus: rejeitado por nao suportar ISAM nativo e logica de negocio
- REST tradicional: ja exists, mas GraphQL oferece flexibilidade de selecao de campos

---

### ADR-002: Schema Code-First vs SDL (Schema Definition Language)

**Estado:** Aceito
**Contexto:** GraphQL suporta dois paradigmas: definir o schema via arquivo `.graphql` (SDL) ou
construi-lo programaticamente (code-first). O Protheus roda em TLPP, uma linguagem tipada
estaticamente com estruturas orientadas a objetos.

**Decisao:** Usar code-first. O schema e construido via classes TLPP (`GqlObjectType`, `GqlField`,
`GqlScalarType`) registradas dinamicamente no `GqlSchema` a partir da configuracao INI.

**Consequencias:**
- Vantagem: schema e gerado automaticamente a partir do dicionario Protheus — nenhuma manutencao manual
- Vantagem: extensibilidade via INI sem recompilacao
- Vantagem: integração natural com o motor de discovery SX3
- Desvantagem: menos visivel (nao ha arquivo `.graphql` para importar em ferramentas)
- Desvantagem: intellisense em IDEs GraphQL standard nao funciona (mas o playground interno suple isso)

**Alternativas consideradas:**
- SDL (*.graphql files): rejeitado por exigir manutencao manual e nao suportar auto-discovery
- GraphQL Code Generator: rejeitado por depender de ferramenta externa

---

### ADR-003: HTML Inline vs CDN para Playground

**Estado:** Aceito
**Contexto:** O playground GraphQL (interface interativa) pode ser implementado usando a biblioteca
GraphiQL via CDN (cdnjs, unpkg) ou gerando HTML auto-contido.

**Decisao:** HTML auto-contido com CSS e JavaScript inline, sem dependencias externas.

**Consequencias:**
- Vantagem: funciona em ambientes sem acesso a internet (comum em empresas com ERP Protheus)
- Vantagem: nenhuma vulnerabilidade de supply chain (CDN comprometido)
- Vantagem: pagina carrega instantaneamente (sem fetch de dependencias)
- Desvantagem: funcionalidades avancadas do GraphiQL (autocomplete, history, settings) nao estao
  presentes — o playground e funcional, mas basico
- Desvantagem: HTML e JavaScript gerados via string concatenation em TLPP, menos legiveis

**Alternativas consideradas:**
- GraphiQL via CDN: rejeitado por dependencia de internet e risco de supply chain
- GraphQL Playground (apollographql): rejeitado pelo mesmo motivo

---

### ADR-004: Configuracao INI vs Banco de Dados

**Estado:** Aceito
**Contexto:** A configuracao dos modulos GraphQL pode ser armazenada em: (a) arquivo INI (appserver.ini),
(b) tabela no banco de dados (ex: SX6 customizado), ou (c) hardcoded em arquivos TLPP.

**Decisao:** Usar arquivo INI (`appserver.ini`) para configuracao, com auto-discovery via SX3 como fallback.

**Consequencias:**
- Vantagem: mudancas so requerem reinicio do appserver, sem deploy de codigo
- Vantagem: arquivo INI e padrao do Protheus — operacoes de infraestrutura ja sabem ler
- Vantagem: auto-discovery SX3 elimina necessidade de listar campos manualmente
- Vantagem: suporte a multi-ambiente (dev/homolog/prod) via arquivos INI diferentes
- Desvantagem: mudancas exigem reinicio do appserver (nao e hot-reload)
- Desvantagem: nao ha versionamento native da configuracao (git nao versiona appserver.ini)
- Desvantagem: concorrencia de leitura (GetIniKey) —acceptable para config estatica

**Alternativas consideradas:**
- Banco de dados (tabela SX6 custom): rejeitado por complexidade adicional e nao-standard
- Hardcoded em TLPP: rejeitado por exigir recompilacao para cada nova tabela
- GraphQL Config Service (servico separado): rejeitado por adicionar dependencia de infraestrutura

---

## 9. Resumo Rápido de Decisoes

| ADR | Decisao | Impacto Principal |
|-----|---------|-------------------|
| ADR-001 | Nativo TLPP (sem Node.js) | Zero infra adicional, mas subset limitado do spec GraphQL |
| ADR-002 | Code-first | Schema gerado automaticamente do dicionario, sem manutencao manual |
| ADR-003 | HTML inline | Playground funciona offline, sem riscos de supply chain |
| ADR-004 | INI + auto-discovery SX3 | Novas tabelas em 3 linhas de INI, sem recompilacao |

---

*Este documento faz parte do projeto GraphQL Protheus v2.0.0. Para perguntas sobre configuracao,
consulte `docs/configuration.md`. Para o guia do consumidor, consulte `docs/self-service-guide.md`.*
