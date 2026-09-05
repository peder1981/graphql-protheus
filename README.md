# Motor Core GraphQL (Protheus)

Servidor GraphQL dinâmico sobre o dicionário de dados do Protheus
(SX2/SX3/SX9), rodando como ponto de entrada REST do AppServer em TLPP.

**Documentação em português brasileiro**: [`docs/como-comecar.md`](docs/como-comecar.md)
(guia rápido), [`docs/manual-implementacao.md`](docs/manual-implementacao.md)
(deploy e configuração) e [`docs/manual-utilizacao.md`](docs/manual-utilizacao.md)
(referência da API GraphQL).

## Endpoint

- `GET /graphql` — nomes dos tipos do schema (lista de bloqueio aplicada)
- `GET /graphql?type=<TABELA>` — detalhe completo do tipo de uma tabela (campos + relacionamentos)
- `GET /graphql?query=<texto GraphQL codificado na URL>` — executa uma consulta

## Exemplo

```
{ SA1(limit: 5, filter: [{field: "A1_COD", op: "eq", value: "000001"}]) {
    A1_COD
    A1_NOME
    SC5 { C5_NUM }
} }
```

## Mutations

`createTABELA`/`updateTABELA`/`deleteTABELA` são expostos apenas para
tabelas listadas em `allowMutations` do `config/graphql-config.json`
(vazio por padrão — nada é gravável até um administrador liberar uma
tabela). Exclusão é sempre lógica (`D_E_L_E_T_ = '*'`), nunca remoção
real de linha.

```
mutation { createSA1(input: {A1_COD: "000123", A1_LOJA: "01", A1_NOME: "Foo"}) {
    A1_COD
    A1_NOME
} }
```

**Limitação conhecida**: veja `docs/architecture.md` para uma ressalva
de concorrência em mutations `create`.

Consulte `docs/architecture.md` e
`docs/superpowers/specs/2026-08-14-graphql-mutations-design.md`.

## Configuração

Veja `docs/configuration.md`. **`compile.sh`/`deploy-rpo.sh` lidam apenas
com fontes `.tlpp` compilados** — `custom/backoffice/graphql/config/graphql-config.json`
precisa ser copiado para o `RootPath` do AppServer separadamente
(verifique `[P12] RootPath=` no `appserver.ini`; o `MemoRead()` resolve
caminhos relativos contra esse `RootPath`, não contra o `SourcePath`,
confirmado testando ambos). Sem esse arquivo, a lista de bloqueio cai
silenciosamente para vazia e toda tabela fica visível — confirmado contra
um servidor real durante o desenvolvimento.

## Arquitetura

Veja `docs/architecture.md` e
`docs/superpowers/specs/2026-08-13-graphql-core-engine-design.md`.

## Validação ao vivo

Resultados capturados contra um AppServer Protheus isolado (container
`protheus-graphql`, REST em `:9996`) — JSON bruto das respostas em
[`docs/screenshots/`](docs/screenshots/).

### 1. Lista de tipos (`GET /graphql`)

Listagem do catálogo de tipos expostos, já com o bloqueio de tabelas
aplicado (`denyTables`).

<img src="docs/screenshots/gql-schema_list.png" alt="Lista de tipos GET /graphql" width="720">
<p><a href="docs/screenshots/schema_list.json"><code>schema_list.json</code></a></p>

### 2. Consulta (`SA1`)

Consulta simples com paginação: `{ SA1(limit: 5) { A1_COD A1_LOJA A1_NOME } }`.

<img src="docs/screenshots/gql-query.png" alt="Consulta SA1" width="720">
<p><a href="docs/screenshots/query.json"><code>query.json</code></a></p>

### 3. Mutation (create → update → delete)

Ciclo completo de escrita com soft-delete: `createSA1` → `updateSA1` →
`deleteSA1` (`D_E_L_E_T_='*'`).

<img src="docs/screenshots/gql-mutation.png" alt="Mutation create/update/delete SA1" width="720">
<p><a href="docs/screenshots/mutation.json"><code>mutation.json</code></a></p>

### 4. Introspection (`SA1`)

Detalhe do tipo `SA1`: campos, tipos e valores expostos via introspection.

<img src="docs/screenshots/gql-introspection.png" alt="Introspection do tipo SA1" width="720">
<p><a href="docs/screenshots/introspection.json"><code>introspection.json</code></a></p>

> **Sobre relacionamentos (SX9):** o motor resolve relações a partir de `SX9`
> (`getRelations`), mas neste deploy de teste a `SX9`/`SIX` não estão
> registradas no `SX2` — por isso campos como `SC5`/`NO1` respondem
> `Unknown field` (degradação documentada no código, "ponytail"). Com um
> dicionário completo, as relações listadas via SX9 são expostas como
> sub-campos aninhados no tipo.

## Testes

Testes TIR (Python e2e) em `tests/tir/`. Execute com `pytest tests/tir/ -v`
contra um AppServer Protheus com este RPO implantado.

## Roteiro de sub-projetos

Este é o sub-projetos 1-2 de 6: Core Engine + Mutations (este repositório)
→ Auth → Field Hooks → SDK Generator → Console PO-UI. Veja as specs de
design para o roteiro completo e como cada sub-projeto posterior se
encaixa neste motor.