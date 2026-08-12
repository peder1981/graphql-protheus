# GraphQL Protheus — Motor GraphQL Nativo para TOTVS Protheus 12

Implementação de um motor GraphQL completo, embarcado no appserver do Protheus 12.1.2510, desenvolvido inteiramente em TLPP.

## Visão Geral

Este projeto implementa o spec GraphQL (parse, validação, execução) de forma nativa em TLPP, sem dependências externas (Node.js, Python, etc.). O motor é exposto via endpoint REST no próprio appserver.

### Principais Características

- **100% TLPP**: parser, validador, executor e schema registry escritos em TLPP puro
- **Zero dependências externas**: roda dentro do appserver Protheus
- **Endpoint REST**: exposto via `/graphql` usando o framework REST nativo
- **Múltiplos módulos**: SA1 (clientes), SB1 (produtos), SC5 (notas fiscais)
- **Paginação**: suporte a `primeiro` e `offset` em queries de lista
- **Filtros dinâmicos**: módulos SA1, SB1 e SC5 suportam filtros por campo
- **Introspecção**: endpoint retorna o schema completo quando query não é fornecida
- **Registro dinâmico**: nova tabelas podem ser registradas via `registerModule()`

## Arquitetura

```
Cliente GraphQL
     │
     │  GET /graphql?query={...}
     ▼
U_GQLSERVICE (Entry Point REST)
     │
     ▼
GqlExecutive (orquestração)
     ├── GqlParser    → AST da query (recursive-descent)
     ├── GqlValidator → validação contra schema
     └── GqlExecutor  → execução dos resolvers
              │
              ▼
         FWExecStatement / TCQuery (queries parametrizadas)
              │
              ▼
         Tabelas Protheus (SA1, SB1, SC5, ...)
```

### Fluxo de Execução

1. `U_GQLSERVICE` lê os parâmetros HTTP (`query`, `filial`)
2. Registra os módulos padrão (SA1, SB1, SC5) no schema
3. `GqlExecutive:executeQuery()` faz o parse da query GraphQL
4. `GqlValidator` valida a AST contra o schema registrado
5. `GqlExecutor` resolve cada campo invocando os codeblocks resolvers
6. Resolvers executam queries SQL via `FWExecStatement` ou `TCQuery`
7. Resultado é retornado como JSON via `FWPrintHTML()`

## Modulos Disponíveis

| Módulo | Tabela | Type GraphQL | Campos | Filtros |
|--------|--------|-------------|--------|---------|
| SA1 | SA1 | `Cliente` | codigo, nome, endereco, bairro, cidade, estado, telefone, tipo, inscricaoEstadual, cgc | tipo, cidade, estado |
| SB1 | SB1 | `Produto` | codigo, descricao, validade, unidademedida, codigobarras, localizacao | palavra (busca na descrição) |
| SC5 | SC5 | `NotaFiscal` | numero, emissao, serie, cliente, serieCF | cliente, dataIni, dataFim |

### Campos por Tipo

**Cliente (SA1)**

| GraphQL | Protheus | Tipo | Descrição |
|---------|----------|------|-----------|
| codigo | A1_COD | String | Código único do cliente |
| nome | A1_NOME | String | Razão social |
| endereco | A1_END | String | Endereço |
| bairro | A1_BAIRRO | String | Bairro |
| cidade | A1_CIDADE | String | Cidade |
| estado | A1_ESTADO | String | Sigla do estado |
| telefone | A1_FONE | String | Telefone |
| tipo | A1_TIPO | String | Tipo (F/J) |
| inscricaoEstadual | A1_INSCRM | String | Inscrição estadual |
| cgc | A1_CGC | String | CGC/CPF |

**Produto (SB1)**

| GraphQL | Protheus | Tipo | Descrição |
|---------|----------|------|-----------|
| codigo | B1_COD | String | Código do produto |
| descricao | B1_DESC | String | Descrição |
| validade | B1_VALID | String (Date) | Data de validade (YMD) |
| unidademedida | B1_UM | String | Unidade de medida |
| codigobarras | B1_CODBARRA | String | Código de barras |
| localizacao | B1_LOCPAD | String | Localização padrão |

**NotaFiscal (SC5)**

| GraphQL | Protheus | Tipo | Descrição |
|---------|----------|------|-----------|
| numero | C5_NUM | String | Número da NF |
| emissao | C5_EMISSAO | String (Date) | Data de emissão (YMD) |
| serie | C5_SERIE | String | Série |
| cliente | C5_CLIENTE | String | Código do cliente |
| serieCF | C5_SERIECF | String | Série CF |

## Configuração

### 1. Copiar arquivos

Copie a pasta `graphql/` inteira para o diretório de fontes do seu projeto Protheus.

### 2. Configurar appserver.ini

Adicione ao arquivo `appserver.ini` do seu ambiente:

```ini
[REST]
/graphql=U_GQLSERVICE
```

Um exemplo completo está disponível em `graphql/config/appserver-graphql.ini`.

### 3. Compilar os fontes

Compile todos os arquivos TLPP na ordem de dependência (veja [DEPLOY.md](DEPLOY.md) para detalhes).

### 4. Reiniciar o appserver

Reinicie o appserver para que as novas configurações REST e o RPO atualizado sejam carregados.

## Uso

### Consulta Simples — Cliente

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

### Lista com Paginação — Clientes

```graphql
{
  listClientes(primeiro: 10, offset: 0, cidade: "SAO PAULO") {
    codigo
    nome
    telefone
  }
}
```

### Busca com Filtro — Produtos

```graphql
{
  listProdutos(palavra: "CANETA", primeiro: 5, offset: 0) {
    produto {
      codigo
      descricao
      unidademedida
    }
  }
}
```

### Nota Fiscal

```graphql
{
  findNotaFiscal(numero: "001234", serie: "1") {
    notaFiscal {
      numero
      emissao
      serie
      cliente
    }
  }
}
```

### Introspecção

```
GET /graphql
→ Retorna o schema completo em JSON
```

### Usando Filial Diferente

```
GET /graphql?query={...}&filial=01
```

## Registro de Módulos Dinâmicos

Para registrar novas tabelas em tempo de execução (sem precisar recompilar):

```tlpp
local oExec := GqlExecutive():new()
oExec:setDefaultFilial("01")
oExec:registerModule("SD1", "ItemNotaFiscal", {"D1_NUM", "D1_ITEM", "D1_PRODUTO", "D1_QUANTID", "D1_PRECO"})
local cResult := oExec:executeQuery("{ listItemNotaFiscal(primeiro: 10) { codigo descricao quantidade } }", "01")
```

O método `registerModule()` cria automaticamente:
- Um `GqlObjectType` com todos os campos mapeados
- Um resolver `list<NomeTipo>` com paginação
- Um resolver `find<NomeTipo>` por chave primária

## Testes

### Testes TIR (TOTVS Interface Robot)

Executar os testes de integração com o appserver:

```bash
pytest tests/tir/ -v
```

### Testes de Unidade (quando disponíveis)

```bash
pytest tests/ -v
```

## Estrutura de Arquivos

```
graphql/
├── core/
│   ├── gqltypes.tlpp          # Tipos base (GqlObject, GqlField, GqlError)
│   ├── gqlschema.tlpp         # Registry de tipos
│   ├── gqlparser.tlpp         # Lexer + Parser GraphQL (recursive-descent)
│   ├── gqlvalidator.tlpp      # Validador de queries
│   ├── gqlexecutor.tlpp       # Executor de queries
│   └── gqlexecutive.tlpp      # Orquestrador principal
├── schema/
│   ├── gqltypesa1.tlpp        # Type definitions SA1 (Cliente)
│   ├── gqltypesb1.tlpp        # Type definitions SB1 (Produto)
│   └── gqltypesc5.tlpp        # Type definitions SC5 (NotaFiscal)
├── resolvers/
│   ├── gqlresolversa1.tlpp    # Resolvers SA1 (initSA1Schema)
│   ├── gqlresolversb1.tlpp    # Resolvers SB1 (initSB1Schema)
│   ├── gqlresolversc5.tlpp    # Resolvers SC5 (initSC5Schema)
│   └── gqlresolvergeneric.tlpp # Resolver generico SX3
├── entrypoints/
│   └── U_GQLSERVICE.tlpp      # Entry point REST /graphql
├── config/
│   └── appserver-graphql.ini  # Configuracao appserver
└── tests/
    └── tir/                   # Testes TIR (a implementar)
```

## Limitacoes e Consideracoes

- **Parsing:** O parser implementa o subset mais comum do GraphQL (queries, campos, argumentos, variáveis, filtros). Não suporta ainda: mutations, subscriptions, fragments, directives (`@skip`, `@include`), `@defer`/`@stream`.
- **Tipos:** Todos os campos são mapeados como `String` por padrão. Tipos `Int`, `Float`, `Boolean`, `Date` requerem extensão manual do schema.
- **Performance:** Cada resolver executa uma query SQL independente. Para cenários com deep nesting, considere implementar DataLoader pattern.
- **Segurança:** Queries são parametrizadas via `FWExecStatement` e `TCQuery` (sem injeção SQL). Rate limiting e complexidade máxima de query devem ser implementados em camada de gateway (nginx/API Gateway).
- **Encoding:** O motor opera em UTF-8. A conversão de/para CP-1252 é feita automaticamente pelo framework REST do Protheus.

### Limitações Conhecidas

| Limitação | Impacto | Mitigação |
|-----------|---------|-----------|
| Mutations não suportadas | Não é possível criar/atualizar/excluir registros | Implementar `GqlMutationType` no futuro |
| Subscriptions não suportadas | Não há WebSocket ou SSE | Usar polling via query |
| Campos Data como String | `B1_VALID` e `C5_EMISSAO` retornam string no formato YMD | Converter no resolver se necessário |
| Paginação SA1 manual | `listClientes` usa `do while` em vez de SQL SKIP/FIRST | Migrar para SQL com SKIP/FIRST |
| Sem rate limiting | Qualquer usuário pode fazer muitas requisições | Implementar no gateway/nginx |
| Sem caching | Cada query executa SQL do zero | Implementar cache de resultados |

## Notas de Segurança

- **Injeção SQL:** As queries usam `FWExecStatement` (queries parametrizadas) e `TCQuery` — não há concatenação direta de strings de usuário na query SQL.
- **Soft-delete:** Todos os resolvers filtram por `D_E_L_E_T_ = ' '` (ou `A1_DELET = ' '` no caso do SA1).
- **Filial:** Todos os resolvers filtram por filial usando `xFilial('TABELA')` ou parâmetro passado via request.
- **NoLock:** Todas as queries usam `%nolock%` para evitar bloqueios de leitura.
- **Logs:** erros são registrados via `FWLogMsg()` e não expostos ao cliente além do padrão GraphQL errors.

## Convenções de Codificação

- Todo código segue o padrão TLPP com `#include "tlpp-core.th"` como primeiro include
- Notação húngara: `c` (character), `n` (numeric), `l` (logical), `a` (array), `o` (object), `b` (codeblock), `x` (variant), `j` (json)
- Todos os métodos públicos possuem documentação ProtheusDOC
- Namespaces usam `custom.graphql`
- Entry points usam prefixo `U_` (exceto o nome da função que é o nome exato do EP)
