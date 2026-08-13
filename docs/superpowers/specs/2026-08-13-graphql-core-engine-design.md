# GraphQL Core Engine — Schema Dinâmico sobre o Dicionário Protheus

Status: aprovado para planejamento
Data: 2026-08-13
Sub-projeto: 1 de 6 (Core Engine → Mutations → Auth → Field Hooks → SDK Generator → Console PO-UI)

## Contexto

O projeto atual (`custom/backoffice/graphql/`) implementa um servidor GraphQL
em TLPP com schema estático escrito à mão por entidade de negócio
(Customer/Invoice/Product) sobre SA1/SB1/SC5 etc. A decisão tomada foi
remover esse projeto por completo e reconstruir um novo servidor GraphQL
nativo Protheus, inspirado nos padrões vistos no repositório de referência
`turbofy-ai/resources` (exemplos do SaaS GraphAPI.io), mas sem portar código
— apenas conceitos (schema, resolvers, subscriptions, codegen).

O novo servidor deve, por padrão, expor **todo o dicionário de dados do
Protheus** (SX2/SX3), restringindo apenas o que for explicitamente
configurado. Isso exige geração de schema **dinâmica**, não mais estática.

Este spec cobre exclusivamente o **Core Engine**: motor de parsing/execução
GraphQL + geração dinâmica de schema + queries de leitura. Mutations, auth
real, hooks de campo, gerador de SDK e o console PO-UI são sub-projetos
posteriores, cada um com seu próprio spec.

## Objetivo

Um motor GraphQL em TLPP capaz de:
1. Responder introspecção (`__schema`, `__type`) listando as tabelas
   Protheus disponíveis (a partir do SX2), respeitando a deny-list.
2. Gerar sob demanda (lazy) o tipo GraphQL completo de uma tabela a partir
   do SX3, com cache em memória.
3. Executar queries de leitura paginadas e filtráveis sobre essas tabelas,
   sempre com `%nolock%`, filtro de filial e `D_E_L_E_T_ = ' '` aplicados
   automaticamente.
4. Resolver campos de relacionamento aninhados usando o dicionário de
   integridade referencial do Protheus (SX9), sob demanda.
5. Bloquear tabelas/campos por uma deny-list de configuração, com um ponto
   de extensão para bloqueio por permissão de usuário (implementado no
   sub-projeto de Auth).

Fora de escopo neste spec: mutations (escrita), autenticação/token real,
subscriptions, hooks de campo customizados, geração de SDK, UI PO-UI.

## Não-objetivos / decisões explícitas

- **Sem reuso do motor atual.** Parser, AST, validator e executor são
  reescritos do zero — o motor atual foi descartado junto com o resto do
  projeto.
- **Sem inferência de relacionamento por convenção de nome.** Relacionamentos
  só são resolvidos via SX9, nunca por heurística de nome de campo.
- **Sem limite de profundidade de aninhamento nesta fase.** Risco de
  N+1/custo de queries profundas é aceito conscientemente e revisitado
  depois, com base em uso real — não é motivo para bloquear release.
- **Sem watch automático de mudança de dicionário.** Cache de schema é
  invalidado manualmente (rotina/endpoint de reload), não por trigger em
  SX2/SX3.

## Arquitetura

```
custom/backoffice/graphql/
  core/
    lexer.tlpp          -- tokenização da query GraphQL
    parser.tlpp          -- AST a partir dos tokens
    validator.tlpp        -- valida AST contra o schema (tipos, campos existentes)
    executor.tlpp         -- percorre AST validada e resolve valores
    schema-provider.tlpp   -- schema dinâmico: introspecção + geração lazy de tipos
    dictionary-reader.tlpp  -- leitura SX2/SX3/SX9 (fonte de verdade do schema)
    access-control.tlpp     -- deny-list de config + ponto de extensão de permissão
    query-builder.tlpp      -- monta FWExecStatement/ChangeQuery a partir da AST resolvida
  config/
    graphql-config.json
  entrypoints/
    (mantém o entrypoint REST atual do AppServer, adaptado ao novo executor)
```

Fluxo de uma query:
`request → lexer → parser (AST) → validator (contra schema-provider) →
executor → query-builder (SQL) → banco → resposta`

## Geração de schema (lazy + cache)

- **Introspecção de alto nível** (`__schema.types`): lista os nomes de
  tabela a partir do SX2, filtrando pela deny-list de tabelas. Não expande
  campos aqui — só nomes/labels.
- **Tipo completo de uma tabela**: gerado na primeira vez que a tabela é
  referenciada (seja por introspecção detalhada `__type(name: "SA1")`, seja
  por uso direto numa query). Mapeamento de tipos SX3 → GraphQL:
  - `C` (Character) → `String`
  - `N` (Numeric) → `Float` (ou `Int` se `X3_DECIMAL == 0`)
  - `D` (Date) → `String` (formato ISO 8601 na serialização)
  - `L` (Logical) → `Boolean`
  - `M` (Memo) → `String`
  - Campos com `X3_VISUAL == "N"` (não visível/oculto) ou já filtrados pela
    deny-list de campos não entram no tipo gerado.
- **Cache**: dicionário em memória (`{ cTable => oGraphQLType }`) por
  processo do AppServer, com TTL configurável em `graphql-config.json`.
  Reload manual via rotina interna (chamada administrativa, não exposta
  como mutation pública nesta fase).

## Relacionamentos via SX9

Quando uma query pede um campo aninhado que não é escalar (ex:
`pedido { cliente { A1_NOME } }`), o `dictionary-reader` consulta o SX9
filtrando por `X9_DOM`/`X9_CDOM` para encontrar a regra de vínculo entre a
tabela corrente e a tabela alvo, usa `X9_EXPDOM`/`X9_EXPCDOM` para montar a
condição de JOIN, e `X9_LIGDOM`/`X9_LIGCDOM` para saber se o resultado é
escalar (1:1) ou lista (1:N) no schema gerado. Resolvido sob demanda por
resolver (não é um JOIN SQL único da query inteira) — aceita o custo de N+1
como trade-off consciente desta fase.

Cache de regras SX9 por par de tabelas, mesmo TTL do cache de schema.

## Execução de queries (filtro, paginação, segurança)

- Toda listagem (campo de tipo lista no schema) exige `limit`/`offset`
  (cursor fica fora de escopo nesta fase). `limit` máximo definido em
  `graphql-config.json` (`maxPageSize`), aplicado mesmo se o cliente pedir
  mais.
- Filtro por campo: operadores `eq`, `gt`, `gte`, `lt`, `lte` sobre campos
  escalares do tipo. Traduzido para bind parameters do `FWExecStatement`
  (nunca concatenação de string) — previne SQL injection.
- Toda query gerada pelo `query-builder` inclui automaticamente, sem
  possibilidade de o cliente sobrescrever:
  - `%nolock%`
  - `<TABELA>_FILIAL = xFilial('<TABELA>')`
  - `D_E_L_E_T_ = ' '`

## Restrição de acesso

Dois mecanismos combinados, avaliados nesta ordem:

1. **Deny-list estrutural** (`graphql-config.json`): lista de tabelas
   bloqueadas por padrão (ex: `SRH*` e demais tabelas de RH sensíveis) e
   campos bloqueados por padrão (ex: qualquer campo cujo nome contenha
   `SENHA`/`_PASSWORD`), mais entradas adicionadas pelo administrador.
   Avaliada primeiro — bloqueio aqui nem aparece na introspecção.
2. **Permissão por usuário** — ponto de extensão
   `AccessControl():AllowField(cTable, cField, oUserContext)`. Nesta fase,
   sem auth real implementada, `oUserContext` é nulo e o método retorna
   sempre `.T.` (permitido) — comentado no código como ponto de integração
   futura com `VerifyAccess`/permissões nativas, a ser conectado no
   sub-projeto de Auth (sub-projeto 3). Nenhum código de negócio deve
   assumir que este método já aplica permissão real nesta fase.

## Configuração

`custom/backoffice/graphql/config/graphql-config.json`:

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

Suporta wildcard simples (`*`) em nomes de tabela/campo. Documentado em
`docs/configuration.md` (recriado como parte da reconstrução).

## Testes (TIR/Python)

Substituem `tests/tir/test_graphql_*.tir` atuais:

- `test_graphql_introspection.tir` — `__schema` lista tabelas permitidas e
  omite as da deny-list.
- `test_graphql_dynamic_type.tir` — `__type(name: "SA1")` reflete campos
  reais do SX3, respeitando deny-list de campo e `X3_VISUAL`.
- `test_graphql_pagination.tir` — listagem respeita `limit`/`offset` e o
  teto de `maxPageSize`.
- `test_graphql_filter.tir` — filtro por campo retorna subconjunto correto;
  tentativa de injection em valor de filtro não quebra a query.
- `test_graphql_relationship.tir` — campo aninhado resolvido via SX9 traz o
  registro relacionado correto (1:1 e 1:N).
- `test_graphql_denylist.tir` — tabela/campo bloqueado nunca aparece nem
  em introspecção nem em resultado de query.

## Migração / remoção do projeto atual

Antes da implementação: remover integralmente
`custom/backoffice/graphql/*`, `tests/tir/*`, `docs/*` (exceto este spec e
o índice de specs), `DEPLOY.md`, `README.md` e `.superpowers/sdd/*`
relativos ao projeto anterior, conforme decidido no brainstorming. README e
docs novos são recriados como parte da entrega deste sub-projeto (mínimo:
README apontando arquitetura + como rodar testes TIR).

## Dependências para sub-projetos seguintes

- **Mutations** (sub-projeto 2) reaproveita `dictionary-reader.tlpp` e
  `schema-provider.tlpp` para tipos de input, e adiciona escrita via
  `FWFormModel`.
- **Auth** (sub-projeto 3) implementa de fato `AccessControl():AllowField`
  e injeta `oUserContext` real a partir do token.
- **Field Hooks** (sub-projeto 4) se pluga no `executor.tlpp` como
  resolver customizável por campo.
- **SDK Generator** (sub-projeto 5) consome `schema-provider.tlpp` para
  gerar contratos AdvPL a partir dos tipos já resolvidos.
- **Console PO-UI** (sub-projeto 6) consome o endpoint REST deste engine
  como qualquer outro cliente GraphQL.
