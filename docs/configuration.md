# GraphQL Protheus — Guia de Configuracao

**Versao:** 2.0.0
**Data:** 2026-08-11

---

## 1. Visao Geral

O motor GraphQL do Protheus utiliza um arquivo de configuracao no formato **INI** (`.ini`) para definir modulos, campos, filtros e comportamentos — **sem necessidade de alterar o codigo TLPP**.

### Como funciona

```
appserver.ini  -->  GqlConfig  -->  GqlExecutive  -->  Schema GraphQL
                                    |
                          GqlAutoDiscover (opcional)
                                    |
                              Dicionario SX3
```

1. Ao iniciar, `GqlConfig` lê a secao `[GraphQL]` do `appserver.ini`
2. `GqlExecutive:loadFromConfig()` percorre os modulos configurados
3. Para cada modulo, usa campos definidos manualmente OU faz auto-discovery via SX3
4. Os modulos habilitados sao registrados automaticamente no schema GraphQL

### Arquivo de configuracao

```
custom/backoffice/graphql/config/appserver-graphql.ini
```

Este arquivo deve ser **copiado para o appserver.ini** do Protheus (ou suas secoes adicionadas manualmente).

---

## 2. Referencia Completa das Chaves INI

### 2.1 Secao [REST]

Define os mapeamentos de URL para os entry points GraphQL.

```ini
[REST]
/graphql              = custom.backoffice.graphql.service.entrypoint
/graphql/playground   = custom.backoffice.graphql.playground.entrypoint
/graphql/schema       = custom.backoffice.graphql.schema.render
/graphql/modules      = custom.backoffice.graphql.modules.render
```

| Path | Funcao |
|------|--------|
| `/graphql` | Endpoint principal de execucao de queries GraphQL |
| `/graphql/playground` | Interface interativa para testar queries |
| `/graphql/schema` | Retorna o schema completo em JSON (introspecao expandida) |
| `/graphql/modules` | Retorna lista de modulos configurados e status do auto-discovery |

---

### 2.2 Secao [GraphQL] — Configuracoes Globais

#### Paginacao padrao

| Chave | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `default.first` | Numerico | `10` | Numero de registros retornados por padrao em queries `list*` |
| `default.maxFirst` | Numerico | `100` | Limite maximo de registros por pagina (hard limit) |
| `default.offset` | Numerico | `0` | Offset padrao para paginacao |

```ini
[GraphQL]
default.first    = 10
default.maxFirst = 100
default.offset   = 0
```

#### Logging

| Chave | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `log.enabled` | Logical | `0` | `1` = habilita logs detalhados via `FWLogMsg()` |
| `log.level` | Texto | `INFO` | Nivel de log: `DEBUG`, `INFO`, `WARN`, `ERROR` |

```ini
[GraphQL]
log.enabled  = 1
log.level    = DEBUG
```

> **Nota:** `log.enabled=1` registra cada modulo carregado, campos descobertos, e erros de execucao no log do appserver.

---

### 2.3 Secao [GraphQL] — Configuracao por Modulo

Cada modulo e definido com um prefixo `module.<nome>.`. O `<nome>` pode ser qualquer identificador (ex: `customer`, `product`, `fornecedor`, `estoque`).

#### Chaves de modulo

| Chave | Obrigatoria | Tipo | Descricao |
|-------|-------------|------|-----------|
| `module.<nome>.table` | Sim | Texto | Alias da tabela Protheus (ex: `SA1`, `SB1`, `SC5`) |
| `module.<nome>.type` | Sim | Texto | Nome do tipo GraphQL (ex: `Cliente`, `Produto`, `NotaFiscal`) |
| `module.<nome>.fields` | Nao* | Texto | Lista de campos separada por virgula |
| `module.<nome>.filter` | Nao | Texto | Campos que poderao ser usados como filtros nas queries |
| `module.<nome>.enabled` | Nao | Logical | `1` = habilitado, `0` = desabilitado |
| `module.<nome>.maxFirst` | Nao | Numerico | Limite de paginacao especifico deste modulo |

> **\*** Se `fields` nao for fornecido e o auto-discovery estiver habilitado, os campos sao obtidos automaticamente do dicionario SX3.

#### Exemplo completo de modulos

```ini
[GraphQL]
; ── Cliente (SA1) ────────────────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO,A1_TIPO
module.customer.enabled    = 1
module.customer.maxFirst   = 50

; ── Produto (SB1) ────────────────────────────────────────────────
module.product.table       = SB1
module.product.type        = Produto
module.product.fields     = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA,B1_LOCPAD
module.product.filter      = B1_DESC
module.product.enabled     = 1

; ── Nota Fiscal (SC5) ────────────────────────────────────────────
module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE,C5_SERIECF
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1

; ── Fornecedores (SA2) — exemplo com auto-discovery ──────────────
module.supplier.table      = SA2
module.supplier.type       = Fornecedor
module.supplier.fields     =
module.supplier.filter     = A2_NOME,A2_CIDADE
module.supplier.enabled    = 1
```

> **Dica:** O campo `module.<nome>.fields` vazio (`=`) ativa o auto-discovery para aquele modulo.

---

### 2.4 Secao [GraphQL] — Auto-Discovery

O auto-discovery consulta o dicionario SX3 do Protheus para encontrar automaticamente os campos de uma tabela.

| Chave | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `module.autoDiscover.enabled` | Logical | `0` | `1` = habilita discovery automatico via SX3 |
| `module.autoDiscover.skipTables` | Texto | `SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL` | Tabelas do dicionario para ignorar (separadas por virgula) |
| `module.autoDiscover.minFields` | Numerico | `3` | Minimo de campos para considerar uma tabela discoverada |

```ini
[GraphQL]
module.autoDiscover.enabled      = 1
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
module.autoDiscover.minFields    = 3
```

#### Como funciona o auto-discovery

1. O sistema consulta `SX1` (dicionario de tabelas) para listar todas as tabelas do banco
2. Para cada tabela (exceto as em `skipTables`), consulta `SX3` (dicionario de campos)
3. Campos com `ADQ_CAMPO` vazio sao ignorados
4. Campos que comecam com `D_E_L_E_T_` ou `XI` sao ignorados
5. Somente tabelas com `>= minFields` campos sao consideradas validas
6. Modulos com `module.<nome>.fields` vazio recebem automaticamente os campos discoverados

**Query executada (internamente):**

```sql
SELECT ADQ_CAMPO
FROM RetSqlName("SX3")
WHERE SX3_FILIAL = '{filial}'
  AND SX3_TABELA = '{tabela}'
  AND ADQ_CAMPO != ''
  AND ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%'
  AND ADQ_CAMPO NOT LIKE 'XI%'
ORDER BY SX3_CPOSX3
```

---

## 3. Guia Passo a Passo

### 3.1 Adicionar uma nova tabela

Para expor uma nova tabela via GraphQL, siga estes 3 passos:

#### Passo 1: Edite o `appserver.ini`

Adicione as linhas abaixo na secao `[GraphQL]`:

```ini
module.<nome>.table   = <TABELA>
module.<nome>.type    = <NomeTipo>
module.<nome>.fields  = <CAMPO1>,<CAMPO2>,<CAMPO3>
module.<nome>.enabled = 1
```

#### Passo 2: Reinicie o appserver

```bash
# No servidor Protheus, reinicie o aplicativo
# Dependendo da instalacao:
srvctl restart appserver
# ou
net stop "TOTVS Application Server"
net start "TOTVS Application Server"
```

#### Passo 3: Verifique se o modulo foi carregado

Acesse o endpoint de modulos:

```
GET http://seuservidor:porta/graphql/modules
```

Ou verifique o log do appserver por:

```
GqlExecutive: loaded module '<nome>' (<TABELA>) with N campos
```

#### Exemplo: Adicionar tabela SA2 (Fornecedores)

```ini
module.supplier.table   = SA2
module.supplier.type    = Fornecedor
module.supplier.fields  = A2_COD,A2_NOME,A2_END,A2_BAIRRO,A2_CIDADE,A2_ESTADO,A2_FONE,A2_TIPO
module.supplier.filter  = A2_NOME,A2_CIDADE
module.supplier.enabled = 1
```

Query resultante disponivel:

```graphql
{
  listFornecedor(primeiro: 10, offset: 0, nome: "ABC") {
    a2Cod
    a2Nome
    a2Cidade
    a2Estado
  }
}
```

---

### 3.2 Desabilitar um modulo

Para desabilitar um modulo sem remove-lo da configuracao:

```ini
module.customer.enabled = 0
```

O modulo sera ignorado pelo `loadFromConfig()` e nao aparecera no schema GraphQL.

Para desabilitar completamente (remover do schema):

1. Defina `enabled = 0` no INI
2. Reinicie o appserver

> **Nota:** Modulos desabilitados nao aparecem em `/graphql/modules` e nao geram entry points no schema.

---

### 3.3 Ajustar paginacao por modulo

#### Paginacao global (todas as tabelas)

```ini
[GraphQL]
default.first    = 20    ; padrao de 20 registros
default.maxFirst = 200   ; maximo de 200 registros
```

#### Paginacao especifica por modulo

```ini
module.customer.maxFirst = 50    ; maximo 50 para clientes
module.product.maxFirst  = 100   ; maximo 100 para produtos
```

> **Nota:** O valor de `maxFirst` por modulo sobrescreve o `default.maxFirst` global. O limite absoluto e o menor entre `default.maxFirst` e `module.<nome>.maxFirst`.

---

### 3.4 Habilitar logging detalhado

```ini
[GraphQL]
log.enabled  = 1
log.level    = DEBUG
```

Logs serao gravados via `FWLogMsg()` e poderao ser observados no log do appserver em tempo real.

**Niveis de log disponiveis:**

| Nivel | Uso |
|-------|-----|
| `DEBUG` | Informacao detalhada de execucao (campos, queries, discover) |
| `INFO` | Eventos principais (modulo carregado, query executada) |
| `WARN` | Avisos (campo nao encontrado, filtro invalido) |
| `ERROR` | Erros de execucao |

---

## 4. Exemplos de Configuracao por Cenario

### 4.1 Desenvolvimento (Dev)

Prioriza discoverabilidade e logs detalhados.

```ini
[REST]
/graphql              = custom.backoffice.graphql.service.entrypoint
/graphql/playground   = custom.backoffice.graphql.playground.entrypoint
/graphql/schema       = custom.backoffice.graphql.schema.render
/graphql/modules      = custom.backoffice.graphql.modules.render

[GraphQL]
; ── Global ──────────────────────────────────────────────────────
default.first    = 10
default.maxFirst = 100
default.offset   = 0

; ── Logging ─────────────────────────────────────────────────────
log.enabled  = 1
log.level    = DEBUG

; ── Auto-Discovery ──────────────────────────────────────────────
module.autoDiscover.enabled      = 1
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX
module.autoDiscover.minFields    = 2

; ── Modulos ─────────────────────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO
module.customer.filter     = A1_NOME,A1_CIDADE
module.customer.enabled    = 1

module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA
module.product.filter      = B1_DESC
module.product.enabled     = 1

module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1
```

### 4.2 Homologacao (Homolog)

Balanco entre performance e debug.

```ini
[REST]
/graphql              = custom.backoffice.graphql.service.entrypoint
/graphql/playground   = custom.backoffice.graphql.playground.entrypoint
/graphql/schema       = custom.backoffice.graphql.schema.render
/graphql/modules      = custom.backoffice.graphql.modules.render

[GraphQL]
; ── Global ──────────────────────────────────────────────────────
default.first    = 20
default.maxFirst = 100
default.offset   = 0

; ── Logging ─────────────────────────────────────────────────────
log.enabled  = 1
log.level    = INFO

; ── Auto-Discovery ──────────────────────────────────────────────
module.autoDiscover.enabled      = 1
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
module.autoDiscover.minFields    = 3

; ── Modulos ─────────────────────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO
module.customer.enabled    = 1
module.customer.maxFirst   = 50

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
```

### 4.3 Producao (Prod)

Maxima performance, logging minimo, auto-discovery desabilitado.

```ini
[REST]
/graphql              = custom.backoffice.graphql.service.entrypoint
/graphql/playground   =
/graphql/schema       =
/graphql/modules      =

[GraphQL]
; ── Global ──────────────────────────────────────────────────────
default.first    = 10
default.maxFirst = 50
default.offset   = 0

; ── Logging ─────────────────────────────────────────────────────
log.enabled  = 0
log.level    = INFO

; ── Auto-Discovery ──────────────────────────────────────────────
module.autoDiscover.enabled      = 0
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
module.autoDiscover.minFields    = 3

; ── Modulos ─────────────────────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME
module.customer.enabled    = 1
module.customer.maxFirst   = 50

module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM
module.product.filter      = B1_COD
module.product.enabled     = 1

module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_CLIENTE
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1
```

> **Nota:** Em producao, desabilite os endpoints de playground e schema para reduzir a superficie de ataque.

---

## 5. Parametros de Sistema (MV)

Parametros globais do Protheus que afetam o comportamento do GraphQL.

| Parametro | Padrao | Descricao | Como definir |
|-----------|--------|-----------|--------------|
| `MV_GQLFIL` | (vazio) | Filial padrao para queries quando `filial` nao e passado na request | `appserver.ini` [CONFIG] ou `SetMV()` |
| `MV_GQLMAXPAGE` | `100` | Limite maximo absoluto de registros por pagina (hard limit) | `appserver.ini` [CONFIG] ou `SetMV()` |
| `MV_GQLLOG` | `0` | `1` = habilita logs adicionais de execucao | `appserver.ini` [CONFIG] ou `SetMV()` |

### Como definir parametros MV

```ini
; No appserver.ini, secao [CONFIG]
[MV]
MV_GQLFIL     = 01
MV_GQLMAXPAGE = 100
MV_GQLLOG     = 0
```

Ou via codigo AdvPL:

```advpl
SetMV("MV_GQLFIL", "01")
SetMV("MV_GQLMAXPAGE", "100")
SetMV("MV_GQLLOG", "1")
```

> **Nota:** `MV_GQLFIL` e usado apenas quando o parametro `filial` nao e fornecido na query GraphQL.

---

## 6. Troubleshooting

### 6.1 Modulo nao aparece no schema

**Sintoma:** Query retorna `Unknown type` ou `Unknown field`.

**Verificacoes:**

1. **Modulo esta habilitado?**
   ```ini
   module.<nome>.enabled = 1
   ```

2. **Tabela e tipo estão definidos?**
   ```ini
   module.<nome>.table   = SA1   ; obrigatorio
   module.<nome>.type    = Cliente  ; obrigatorio
   ```

3. **Campos existem?**
   - Se `fields` estiver vazio, verifique se `autoDiscover.enabled = 1`
   - Verifique se a tabela existe no dicionario SX1
   - Verifique se a tabela tem pelo menos `minFields` campos no SX3

4. **Appserver foi reiniciado?**
   - Mudancas no INI so entram em vigor apos reinicio do appserver

### 6.2 Auto-discovery nao encontra campos

**Sintoma:** Modulo carregado mas com 0 campos.

**Verificacoes:**

1. Verifique se `module.autoDiscover.enabled = 1`
2. Verifique se a tabela nao esta em `skipTables`
3. Verifique a query diretamente no banco:
   ```sql
   SELECT ADQ_CAMPO
   FROM SX3
   WHERE SX3_TABELA = 'SA1'
     AND ADQ_CAMPO != ''
     AND ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%'
     AND ADQ_CAMPO NOT LIKE 'XI%'
   ```
4. Aumente `module.autoDiscover.minFields` se necessario (padrao = 3)

### 6.3 Erro 404 em `/graphql`

**Sintoma:** Endpoint nao acessivel.

**Verificacoes:**

1. Entrada `[REST]` existe no appserver.ini?
   ```ini
   [REST]
   /graphql = custom.backoffice.graphql.service.entrypoint
   ```

2. O entry point `GQLSERVICE` esta compilado no RPO?
   ```bash
   # Verificar se o simbolo existe
   # No TOTVS Developer Studio: View > Show Symbol Table
   ```

3. O namespace esta correto?
   - O modulo deve estar em `custom/backoffice/graphql/`
   - O arquivo deve ter extensao `.tlpp`

### 6.4 Query retorna `null` para campo

**Sintoma:** Campos validos no schema mas retornam `null`.

**Verificacoes:**

1. **Soft-delete:** O campo `D_E_L_E_T_` da tabela esta limpo (`' '`)?
   ```sql
   SELECT D_E_L_E_T_ FROM SA1 WHERE A1_COD = '01'
   ```

2. **Filial:** A query esta usando a filial correta?
   - Verifique `MV_GQLFIL` ou o parametro `filial` na query

3. **Campo nao existe:** O campo esta realmente na tabela?
   ```sql
   SELECT SX3_CAMPO FROM SX3 WHERE SX3_TABELA = 'SA1' AND SX3_CAMPO = 'A1_NOME'
   ```

### 6.5 Paginacao nao funciona

**Sintoma:** Parametros `primeiro` e `offset` sao ignorados.

**Verificacoes:**

1. Verifique se os parametros estao sendo passados corretamente na query:
   ```graphql
   {
     listCliente(primeiro: 10, offset: 20) {
       a1Cod
       a1Nome
     }
   }
   ```

2. Verifique os limites:
   - `default.maxFirst` no INI
   - `MV_GQLMAXPAGE` (hard limit do sistema)
   - `module.<nome>.maxFirst` (limite por modulo)

3. O valor de `primeiro` nao pode exceder o menor limite entre essas configuracoes.

### 6.6 Logs não aparecem

**Sintoma:** `log.enabled = 1` mas nenhum log e gerado.

**Verificacoes:**

1. Verifique se o log do appserver esta configurado para o nivel adequado
2. Verifique se `FWLogMsg()` esta funcionando no ambiente
3. Confirme que o appserver foi reiniciado apos alterar `log.enabled`

---

## 7. Fluxo de Inicializacao

```
Appserver inicia
      │
      ▼
GqlConfig():new()
      │
      ├─ Read [GraphQL] section from appserver.ini
      ├─ Parse global defaults (first, maxFirst, offset, log)
      ├─ Parse auto-discovery settings
      └─ discoverModules() → scan for module.*.table keys
      │
      ▼
GqlExecutive():new()
      │
      ├─ Create GqlConfig instance
      ├─ Create GqlAutoDiscover instance
      └─ loadFromConfig()
            │
            ├─ For each module:
            │   ├─ Is enabled? → skip if no
            │   ├─ Has fields? → use manual fields
            │   └─ No fields? → auto-discover via SX3
            │
            └─ registerModule(table, type, fields)
                  │
                  └─ Add to GqlSchema
                        │
                        └─ GraphQL ready to serve queries
```

---

## 8. Resumo Rápido

| Tarefa | Acao |
|--------|------|
| Adicionar tabela | 3 linhas no INI + reiniciar appserver |
| Desabilitar modulo | `module.<nome>.enabled = 0` + reiniciar |
| Ajustar paginacao global | `default.first` / `default.maxFirst` no INI |
| Ajustar paginacao por modulo | `module.<nome>.maxFirst` no INI |
| Habilitar auto-discovery | `module.autoDiscover.enabled = 1` |
| Habilitar logging | `log.enabled = 1` + reiniciar |
| Mudar filial padrao | `MV_GQLFIL = 01` no [CONFIG] |
| Verificar modulos | `GET /graphql/modules` |
| Testar query | `GET /graphql/playground` |
