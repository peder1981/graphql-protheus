# Deploy — GraphQL Protheus

## Pre-requisitos

- TOTVS Protheus 12.1.2510 ou superior
- Appserver configurado com suporte a REST
- TLPP compiler disponivel
- Tabelas SA1, SB1, SC5 presentes no banco de dados

## Passo a Passo

### 1. Copiar arquivos

Copie a pasta `custom/backoffice/graphql/` inteira para o diretorio de fontes do projeto.

### 2. Configurar appserver.ini

Adicione ao arquivo `appserver.ini` do seu ambiente:

```ini
[REST]
/graphql              = custom.backoffice.graphql.service.entrypoint
/graphql/playground   = custom.backoffice.graphql.playground.entrypoint
/graphql/schema       = custom.backoffice.graphql.schema.render
/graphql/modules      = custom.backoffice.graphql.modules.render

[GraphQL]
; ── Global ──────────────────────────────────────────────────────
default.first     = 10
default.maxFirst  = 100
default.offset    = 0

; ── Logging ─────────────────────────────────────────────────────
log.enabled       = 0
log.level         = INFO

; ── Modulo: Cliente (SA1) ──────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO,A1_TIPO
module.customer.enabled    = 1

; ── Modulo: Produto (SB1) ──────────────────────────────────────
module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA,B1_LOCPAD
module.product.filter      = B1_DESC
module.product.enabled     = 1

; ── Modulo: Nota Fiscal (SC5) ──────────────────────────────────
module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE,C5_SERIECF
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1

; ── Auto-Discovery (opcional) ──────────────────────────────────
module.autoDiscover.enabled      = 0
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
module.autoDiscover.minFields    = 3
```

Se ja existirem entradas em `[REST]`, adicione as novas linhas no final da secao.

### 3. Compilar os fontes

Compile todos os arquivos TLPP na ordem correta (dependencias):

1. `core/types.tlpp`
2. `core/schema.tlpp`
3. `core/parser.tlpp`
4. `core/validator.tlpp`
5. `core/executor.tlpp`
6. `core/executive.tlpp`
7. `core/config.tlpp`
8. `core/autodiscover.tlpp`
9. `schema/customer.types.tlpp`
10. `schema/product.types.tlpp`
11. `schema/invoice.types.tlpp`
12. `resolvers/customer.init.tlpp`
13. `resolvers/product.init.tlpp`
14. `resolvers/invoice.init.tlpp`
15. `resolvers/generic.tlpp`
16. `service.entrypoint.tlpp`
17. `playground.tlpp`
18. `playground.entrypoint.tlpp`
19. `schema.render.tlpp`
20. `modules.render.tlpp`

Use o comando de compilacao padrao do Protheus ou TOTVS Developer Studio.

### 4. Reiniciar o appserver

```bash
# Parar o appserver
./stopserver.sh

# Iniciar o appserver
./startserver.sh
```

### 5. Testar o endpoint

```bash
# Teste basico — introspeccao
curl "http://seu-servidor:porta/rest/graphql"

# Teste com query
curl "http://seu-servidor:porta/rest/graphql?query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7D%20%7D"

# Teste com filial especifica
curl "http://seu-servidor:porta/rest/graphql?query=%7B%20listCliente(primeiro%3A%205)%20%7D&filial=01"
```

### 6. Verificar modulos configurados

```bash
curl "http://seu-servidor:porta/graphql/modules"
```

A resposta deve incluir os modulos `customer`, `product` e `invoice` com `enabled: true`.

### 7. Executar testes TIR

```bash
pytest tests/tir/test_graphql_sa1.tir -v
pytest tests/tir/test_graphql_sb1.tir -v
```

---

## Configuracao Pos-Deploy

### Verificar auto-discovery

Se desejar habilitar auto-discovery de novas tabelas:

```ini
[GraphQL]
module.autoDiscover.enabled      = 1
module.autoDiscover.minFields    = 3
```

Após habilitar e reiniciar o appserver, verifique quais tabelas foram descobertas:

```bash
curl "http://seu-servidor:porta/graphql/modules"
```

O campo `autoDiscover.tablesDiscovered` mostrara a quantidade de tabelas encontradas no dicionario SX1.

### Acessar o playground

Abra o navegador e acesse:

```
http://seu-servidor:porta/graphql/playground
```

O playground permite:
- Escrever e executar queries GraphQL
- Ver exemplos de queries por modulo
- Explorar tipos disponiveis no menu lateral
- Ver status dos modulos (ON/OFF)

> **Nota:** Em producao, considere desabilitar o playground e os endpoints de schema/modules para reduzir a superficie de ataque:
> ```ini
> [REST]
> /graphql/playground   =
> /graphql/schema       =
> /graphql/modules      =
> ```

### Validar modulos via /graphql/modules

O endpoint retorna:
- Lista de modulos com suas tabelas, campos e status
- Configuracao global (paginacao, logging, auto-discovery)
- Resultado do auto-discovery (tabelas descobertas e ignoradas)

Use para diagnosticar problemas pos-deploy e confirmar que todos os modulos esperados estao carregados.

---

## Parametros de Sistema (MV)

| Parametro | Padrao | Descricao |
|-----------|--------|-----------|
| `MV_GQLFIL` | (vazio) | Filial padrao para queries GraphQL quando nao informada na request |
| `MV_GQLMAXPAGE` | `100` | Maximo de registros por pagina (hard limit) |
| `MV_GQLLOG` | `0` | 1 = habilitar logs detalhados de execucao |

---

## Monitoramento

Os logs de execucao GraphQL sao gravados via `FWLogMsg()` no log padrao do appserver. Para habilitar log detalhado:

1. Defina `log.enabled = 1` na secao `[GraphQL]` do appserver.ini
2. Reinicie o appserver
3. Verifique o log do appserver em tempo real

Logs de sucesso incluem:
```
GqlExecutive: loaded module 'customer' (SA1) with 10 campos
GqlExecutive: registered field 'a1Cod' on type 'Cliente'
```

Logs de erro incluem:
```
GqlExecutive: module 'supplier' is disabled, skipping
GqlExecutive: no fields for module 'supplier', skipping
```

---

## Troubleshooting

| Problema | Solucao |
|----------|---------|
| Erro 404 em `/graphql` | Verificar se entrada `[REST] /graphql=custom.backoffice.graphql.service.entrypoint` existe no appserver.ini |
| Erro de compilacao em `types.tlpp` | Verificar se `tlpp-core.th` e `totvs.ch` estao disponiveis no RPO |
| Query retorna `null` para campo | Verificar se o campo existe na tabela e se o soft-delete (`D_E_L_E_T_`) esta limpo |
| Erro `Unknown field` | Verificar se o tipo foi registrado via configuracao INI ou se o resolver esta definido |
| Paginacao nao funciona | Verificar se os parametros `primeiro` e `offset` estao sendo passados corretamente |
| Modulo nao aparece em `/graphql/modules` | Verificar se `module.<nome>.enabled = 1` e se o appserver foi reiniciado apos a alteracao |
| Auto-discovery nao encontra campos | Verificar se `module.autoDiscover.enabled = 1` e se a tabela nao esta em `skipTables` |
| Playground retorna 404 | Verificar se a entrada `[REST] /graphql/playground` existe no appserver.ini |
