# GraphQL Protheus — Self-Service Buffet & Configurabilidade

**Data:** 2026-08-11
**Status:** Design aprovado
**Escopo:** Configuracao via INI, auto-discovery SX3, playground interativo, documentacao integral

---

## 1. Visao Geral

O GraphQL Protheus atual funciona, mas exige que o desenvolvedor **toque no codigo TLPP** para adicionar novas tabelas. Esta evolucao transforma o sistema em um **self-service buffet**: qualquer consumidor pode descobrir, explorar e usar os dados do ERP editando apenas arquivos de configuracao, sem recompilar.

### Principais mudancas

| Antes | Depois |
|-------|--------|
| Modulos hardcoded no entrypoint | Modulos definidos no appserver.ini |
| Campos fixos por tabela | Campos definidos por INI + auto-discovery SX3 |
| Sem interface de exploracao | Playground HTML inline servido pelo appserver |
| Documentacao basica | Docs completos (API ref, configuracao, arquitetura, self-service) |

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CONSUMIDORES                                │
│  GraphQL Client   │   Playground    │   Docs      │   Scripts      │
└────────┬──────────┴────────┬────────┴──────┬──────┴────────┬───────┘
         │                   │               │               │
         ▼                   ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   PROTHEUS APPSERVER 12.1.2510                     │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              REST Layer (appserver.ini)                      │   │
│  │  /graphql          → GQLSERVICE (existing)                  │   │
│  │  /graphql/playground → GQLPLAYGROUND (new)                  │   │
│  │  /graphql/schema   → GQLSCHEMARENDER (new)                  │   │
│  │  /graphql/modules  → GQLMODULES (new)                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              GraphQL Core (existing, no changes)             │   │
│  │  GqlParser → GqlValidator → GqlExecutor                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              NEW: Configuracao + Discovery                   │   │
│  │  GqlConfig        — parse INI, exposes settings             │   │
│  │  GqlAutoDiscover  — consulta SX3, popula campos             │   │
│  │  GqlPlayground    — gera HTML interativo                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              NEW: Entrypoints REST                           │   │
│  │  custom.backoffice.graphql.playground.entrypoint            │   │
│  │  custom.backoffice.graphql.schema.render                    │   │
│  │  custom.backoffice.graphql.modules.render                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Dados (existing)                                │   │
│  │  SA1, SB1, SC5, ... via FWExecStatement                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Configurabilidade

### 3.1 Estrutura do INI

Nova secao `[GraphQL]` no appserver.ini (adicional a `[REST]`):

```ini
[GraphQL]
; ── Global ──────────────────────────────────────────────────────
; Paginacao padrao
default.first     = 10
default.maxFirst  = 100
default.offset    = 0

; Logging
log.enabled       = 0
log.level         = INFO

; ── Modulo: SA1 (Clientes) ──────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO,A1_TIPO
module.customer.enabled    = 1
module.customer.maxFirst   = 50

; ── Modulo: SB1 (Produtos) ──────────────────────────────────────
module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA,B1_LOCPAD
module.product.filter      = B1_DESC
module.product.enabled     = 1

; ── Modulo: SC5 (Notas Fiscais) ─────────────────────────────────
module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE,C5_SERIECF
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1

; ── Auto-Discovery via SX3 ──────────────────────────────────────
module.autoDiscover.enabled      = 1
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
module.autoDiscover.minFields    = 3
```

### 3.2 Prioridade de configuracao

Ao registar um modulo, a ordem de precedence é:

1. **Campos especificados manualmente** em `module.*.fields` → usam estes
2. **Auto-discovery** via SX3 → usa campos descobertos automaticamente
3. **Fallback hardcoded** → mantem SA1/SB1/SC5 se nada configurado

### 3.3 Classe GqlConfig

**File:** `custom/backoffice/graphql/core/config.tlpp`

```tlpp
class GqlConfig
    method new()                          — parseia appserver.ini secao [GraphQL]
    method getModuleKeys() as array       — retorna array de chaves de modulo ("customer", "product", ...)
    method getModuleField(cModule, cKey)  — retorna valor de chave especifica do modulo
    method isModuleEnabled(cModule)       — retorna .T. se modulo esta habilitado
    method getDefaultFirst() as numeric   — pagina padrao
    method getMaxFirst() as numeric       — limite maximo de paginacao
    method isLogEnabled() as logical      — logging lig/deslig
endclass
```

### 3.4 Classe GqlAutoDiscover

**File:** `custom/backoffice/graphql/core/autodiscover.tlpp`

```tlpp
class GqlAutoDiscover
    method new(oConfig as object)
    method discover() as json
        // Consulta SX3 para todas as tabelas (exceto skipTables)
        // Retorna: {"SA1": {"fields": ["A1_COD", ...], "count": 120}, ...}
    method getTableFields(cTable as character) as array
        // Retorna campos de uma tabela especifica
    method isSkipTable(cTable as character) as logical
endclass
```

Query de discovery:
```sql
SELECT SX3_CPOSX3, ADQ_CAMPO
FROM RetSqlName("SX3")
WHERE SX3_FILIAL = '{filial}'
  AND SX3_DELET  = ' '
  AND ADQ_CAMPO  != ''
  AND ADQ_CAMPO  NOT LIKE 'D_E_L_E_T_%'
ORDER BY SX3_CPOSX3
```

### 3.5 Atualizacao do GqlExecutive

O `executive.tlpp` existente recebe dois metodos novos:

```tlpp
method loadFromConfig(oConfig as object) as object
    // Percorre módulos configurados no INI
    // Para cada módulo enabled:
    //   1. Verifica se campos estão definidos manualmente
    //   2. Se não, usa auto-discovery para populá-los
    //   3. Chama registerModule(cTable, cTypeName, aFields)

method getModuleMetadata() as json
    // Retorna JSON com lista de módulos, campos, filtros, enabled status
    // Usado pelo endpoint /graphql/modules
```

---

## 4. Self-Service Playground

### 4.1 Endpoint

| Path | Entry Point | Descricao |
|------|-------------|-----------|
| `/graphql/playground` | `custom.backoffice.graphql.playground.entrypoint` | Interface interativa |
| `/graphql/schema` | `custom.backoffice.graphql.schema.render` | Schema JSON (introspecao expandida) |
| `/graphql/modules` | `custom.backoffice.graphql.modules.render` | Lista de modulos configurados |

### 4.2 Classe GqlPlayground

**File:** `custom/backoffice/graphql/playground.tlpp`

```tlpp
class GqlPlayground
    method new(oSchema as object, oConfig as object)
    method render() as character
        // Gera HTML completo com:
        // 1. Sidebar com lista de tipos GraphQL
        // 2. Area de query builder (campos selecionaveis)
        // 3. Botao execute → chama /graphql?query=...
        // 4. Area de resposta JSON
        // 5. Examples por modulo
        // 6. Info de configuracao (modulos, filtros disponiveis)
```

### 4.3 HTML auto-contido

O HTML gerado NAO depende de CDN externo. Tudo inline:
- CSS: embedded no `<style>`
- JS: embedded no `<script>` (fetch para `/graphql`, manipulação do DOM)
- Icons: SVG inline

### 4.4 Funcionalidades do Playground

| Funcionalidade | Descricao |
|---------------|-----------|
| **Type Explorer** | Click no nome do tipo mostra todos os campos disponiveis |
| **Query Builder** | Checkboxes para selecionar campos; monta query automaticamente |
| **Filter Helpers** | Campos listados em `module.*.filter` aparecem como inputs de filtro |
| **Pagination Controls** | Inputs para `primeiro` e `offset` |
| **Execute** | Botao que chama `/graphql` com a query montada e mostra resultado |
| **Examples** | Querys prontas por tipo: "find by code", "list with filter", "list all" |
| **Schema Info** | Badge mostrando total de tipos, campos, modulos ativos |
| **Config Status** | Mostra se auto-discovery esta ativo, quantas tabelas descobertas |

---

## 5. Documentacao Integral

### 5.1 Arquivos a criar

```
docs/
├── api-reference.md          # 800+ linhas
├── configuration.md          # 600+ linhas
├── architecture.md           # 500+ linhas
├── self-service-guide.md     # 400+ linhas
└── changelog.md              # historico de versoes
```

### 5.2 Conteudo de cada arquivo

**api-reference.md:**
```
1. Visao geral da API
2. Esquema GraphQL completo (todos os tipos)
3. Tabela de mapeamento Protheus → GraphQL
4. Operacoes por modulo
   - find{Type}(codigo: String!): {Type}
   - list{Type}(primeiro: Int, offset: Int, ...filtros): [{Type}]
5. Exemplos de query (10+ exemplos)
6. Tratamento de erros
7. Introspecao (como usar /graphql/schema)
```

**configuration.md:**
```
1. Visao geral da configuracao
2. Secao [GraphQL] — referencia completa de cada chave
3. Secao [REST] — mapeamento de endpoints
4. Auto-discovery SX3 — como funciona, como configurar
5. Guia: adicionar uma nova tabela
6. Guia: desabilitar um modulo
7. Guia: ajustar paginacao por modulo
8. Guia: habilitar logging
9. Exemplos de configuracao (dev, homolog, prod)
10. Variaveis de sistema (MV_GQL*)
```

**architecture.md:**
```
1. Visao geral do sistema
2. Diagrama C4 Level 1 (Context)
3. Diagrama C4 Level 2 (Container)
4. Fluxo de execucao de uma query (passo a passo)
5. Modelo de configuracao (INI → GqlConfig → GqlExecutive)
6. Modelo de auto-discovery (SX3 → GqlAutoDiscover)
7. Extensibilidade (como adicionar novos tipos)
8. Decisoes arquiteturais (ADR)
   - ADR-001: GraphQL nativo vs Node.js
   - ADR-002: Schema code-first vs SDL
   - ADR-003: HTML inline vs CDN para playground
```

**self-service-guide.md:**
```
1. "Minha primeira query" — tutorial passo a passo
2. Como usar o playground (capturas de tela descritivas)
3. Como descobrir o que está disponivel (introspecao)
4. Como montar queries com filtros
5. Como navegar a paginacao
6. FAQ
   - "Quais tabelas posso consultar?"
   - "Como vejo todos os campos de uma tabela?"
   - "Posso filtrar por X campo?"
   - "Por que recebo null para um campo?"
   - "Como adiciono uma tabela que nao está na lista?"
7. Troubleshooting para consumidores
```

### 5.3 Atualizacoes nos docs existentes

**README.md** — adicionar secoes:
- Self-service: como explorar sem ler docs
- Configuracao rapida: 3 passos para adicionar uma tabela
- Playground: link para `/graphql/playground`
- Tabela de todos os modulos disponiveis

**DEPLOY.md** — adicionar secoes:
- Configuracao pos-deploy: editar appserver.ini
- Auto-discovery: como verificar tabelas descobertas
- Playground: como acessar a interface
- Testes de validacao: verificar modulos via `/graphql/modules`

---

## 6. Novos Arquivos (Resumo)

```
custom/backoffice/graphql/
├── core/
│   ├── config.tlpp            [NOVO] — GqlConfig: parse e acesso ao INI
│   ├── autodiscover.tlpp      [NOVO] — GqlAutoDiscover: descoberta SX3
│   ├── types.tlpp             [EXISTENTE, sem mudancas]
│   ├── schema.tlpp            [EXISTENTE, sem mudancas]
│   ├── parser.tlpp            [EXISTENTE, sem mudancas]
│   ├── validator.tlpp         [EXISTENTE, sem mudancas]
│   ├── executor.tlpp          [EXISTENTE, sem mudancas]
│   └── executive.tlpp         [ATUALIZADO] — loadFromConfig(), getModuleMetadata()
├── playground.tlpp            [NOVO] — GqlPlayground: gera HTML
├── schema/                    [EXISTENTE, sem mudancas]
├── resolvers/                 [EXISTENTE, sem mudancas]
├── playground.entrypoint.tlpp [NOVO] — EP REST /graphql/playground
├── schema.render.tlpp         [NOVO] — EP REST /graphql/schema
├── modules.render.tlpp        [NOVO] — EP REST /graphql/modules
├── service.entrypoint.tlpp    [EXISTENTE, sem mudancas]
└── config/
    └── appserver-graphql.ini  [ATUALIZADO] — secao [GraphQL] completa

docs/
├── api-reference.md           [NOVO]
├── configuration.md           [NOVO]
├── architecture.md            [NOVO]
├── self-service-guide.md      [NOVO]
└── changelog.md               [NOVO]
```

---

## 7. Regras de Negocio (Global Constraints)

- **Runtime:** tudo no appserver Protheus 12.1.2510 — sem Node.js
- **Encoding:** CP-1252 em todos `.tlpp`
- **No IIF:** explicito `If/Else/EndIf` (SonarQube CA4000)
- **No ConOut:** usar `FWLogMsg()`
- **Namespace:** `custom.backoffice.graphql`
- **Nomenclatura TOTVS:** lowercase com ponto, sem underscore, PascalCase classes, camelCase metodos
- **Soft-delete:** sempre `D_E_L_E_T_ = ' '`
- **Filial:** sempre `xFilial('XXX')`
- **ProtheusDOC:** todo metodo com doc block

---

## 8. Testes

**Novos testes TIR:**
- `tests/tir/test_graphql_config.tir` — validar parse de INI, modulos habilitados/desabilitados
- `tests/tir/test_graphql_playground.tir` — validar endpoint `/graphql/playground` retorna HTML
- `tests/tir/test_graphql_modules.tir` — validar endpoint `/graphql/modules` retorna JSON com modulos
- `tests/tir/test_graphql_autodiscover.tir` — validar descoberta de campos via SX3

**Testes existentes:** todos mantidos e atualizados para novos endpoints.

---

## 9. Critérios de Aceitacao

- [ ] Novo modulo adicionado apenas editando appserver.ini (sem tocar em TLPP)
- [ ] Playground acessivel em `/graphql/playground` sem dependencias externas
- [ ] Introspecao expandida retorna todos os tipos + campos + filtros
- [ ] Endpoint `/graphql/modules` retorna lista de modulos configurados
- [ ] Auto-discovery SX3 funciona e popula campos quando `module.*.fields` esta vazio
- [ ] Documentacao cobre todos os 5 documentos especificados
- [ ] Zero `iif()`, zero `ConOut()`, CP-1252 em todos arquivos
- [ ] Todos os testes TIR passam
