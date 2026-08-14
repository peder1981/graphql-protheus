# GraphQL Mutations — Escrita sobre o Dicionário Protheus

Status: aprovado para planejamento
Data: 2026-08-14
Sub-projeto: 2 de 6 (Core Engine → **Mutations** → Auth → Field Hooks → SDK Generator → Console PO-UI)

## Contexto

O Core Engine (sub-projeto 1, mesclado em `main`) entrega leitura: schema
dinâmico gerado do SX2/SX3/SX9, deny-list de tabelas/campos, queries
paginadas e filtráveis, relacionamentos aninhados. O parser já reconhece a
palavra-chave `mutation` como tipo de operação (construído antecipadamente
no sub-projeto 1), mas nenhum executor de escrita existe ainda.

Este spec cobre exclusivamente **mutations**: criar, atualizar e excluir
registros via GraphQL sobre as mesmas tabelas expostas pelo Core Engine.
Auth real, hooks de campo, SDK e console PO-UI continuam fora de escopo.

**Desvio da previsão do spec anterior:** o spec do Core Engine especulava
escrita via `FWFormModel` (MVC). Decisão tomada neste spec: **SQL raw**
(mesmo estilo do `query-builder.tlpp` existente — `TCQuery`/execução direta,
valores sempre escapados via `EscapeValue()`), não MVC. Motivo: MVC exige
um model por rotina, incompatível com a abordagem genérica
dicionário-orientada que todo o Core Engine já usa para leitura. O custo
aceito conscientemente: nenhuma validação automática do Protheus (SX7
triggers, regras de negócio de rotina) roda no caminho de escrita — só o
que este spec define explicitamente (obrigatoriedade/tipo/tamanho do SX3).

## Objetivo

Um caminho de escrita GraphQL capaz de:

1. Expor `createTABLE(input)`, `updateTABLE(input)`, `deleteTABLE(input)`
   para cada tabela explicitamente liberada em `allowMutations`.
2. Validar o input contra os metadados SX3 (obrigatório, tipo, tamanho)
   antes de qualquer escrita.
3. Escrever via SQL direto, sempre com filial forçada (`cFilAnt`, nunca o
   valor enviado pelo cliente) e `D_E_L_E_T_ = ' '` nas condições de
   update/delete.
4. Aplicar exclusão como soft-delete (`D_E_L_E_T_ = '*'`), consistente com
   o resto do Protheus e com o filtro que toda query já aplica.
5. Devolver o registro afetado reaproveitando o caminho de leitura já
   existente (`GqlExecutor`), moldado pelo selection set pedido na
   mutation — sem duplicar lógica de seleção de campos.

Fora de escopo: `FWFormModel`/MVC, SX7 triggers, geração automática de
chave via SX5/`GetSxeNum()`, mutations em lote, subscriptions, auth real
por usuário (permissão continua via `GqlAccessControl`, mesmo estado do
sub-projeto 1 — sempre `.T.` até o sub-projeto 3).

## Não-objetivos / decisões explícitas

- **Sem MVC.** Ver "Desvio" acima.
- **Sem allow-list unificada com leitura.** Mutations usam uma allow-list
  própria (`allowMutations`), separada da deny-list de leitura — nada é
  escrevível por padrão, mesmo que já seja legível.
- **Sem geração automática de chave.** O cliente sempre envia o(s) campo(s)
  de chave no `input`, inclusive em `create`. `GetSxeNum()`/numeração
  automática SX5 fica fora de escopo — quem precisar, gera a chave antes de
  chamar a mutation.
- **Sem hard delete.** Exclusão é sempre `D_E_L_E_T_ = '*'`.
- **Sem validação além de obrigatório/tipo/tamanho do SX3.** Fórmulas de
  `X3_VALID`, domínios SX5, regras cruzadas entre campos e triggers SX7
  não são replicados nesta fase.

## Arquitetura

```
custom/backoffice/graphql/
  core/
    ...(arquivos existentes do Core Engine, inalterados na interface)...
    mutation-schema.tlpp    -- gera tipos create/update/deleteTABLE a partir
                               do dictionary-reader + allowMutations
    input-validator.tlpp     -- valida input contra SX3 (obrigatório/tipo/tamanho)
    mutation-builder.tlpp    -- monta SQL de INSERT/UPDATE (soft-delete) a
                               partir do input validado
    mutation-executor.tlpp   -- orquestra: parse (já existente) → valida
                               operação=mutation → valida input → escreve →
                               re-seleciona via GqlExecutor → responde
  config/
    graphql-config.json      -- + campo "allowMutations": []
```

Fluxo de uma mutation:
`request → lexer (existente) → parser (existente, já entende "mutation") →
GqlMutationExecutor → valida tabela contra allowMutations → GqlInputValidator
(SX3) → GqlMutationBuilder (SQL) → banco → GqlExecutor re-seleciona a linha
afetada pela chave → resposta moldada pelo selection set`

`GqlExecutor` (leitura) e `GqlMutationExecutor` (escrita) são pares no mesmo
nível — o entrypoint despacha para um ou outro conforme
`oDocument["definitions"][1]["operation"]` (`"query"` vs `"mutation"`),
igual ao parser já expõe hoje sem uso.

## Schema de mutations (tipos gerados)

- Para cada `cTable` em `allowMutations` (e que passa pela deny-list de
  leitura — uma tabela negada em `denyTables` nunca vira mutation, mesmo se
  alguém a colocar em `allowMutations` por engano): três campos raiz no tipo
  `Mutation`: `create<TABLE>`, `update<TABLE>`, `delete<TABLE>`.
- Cada campo recebe um único argumento `input`, tipo `<TABLE>Input` — objeto
  plano com os mesmos campos que `GqlDictionaryReader:getTableFields()` já
  produz para leitura (mesmo filtro de `denyFields`/`X3_VISUAL`), sem
  distinção estrutural entre campos de chave e não-chave no tipo do schema
  (a distinção é decidida em tempo de execução via `getOrderKey()`).
- Tipo de retorno de todos os três: `<TABLE>` (o mesmo tipo já gerado para
  leitura) — o cliente reseleciona campos exatamente como faria numa query.
- Cache do tipo de mutation segue o mesmo TTL/reload do
  `GqlSchemaProvider` existente (`getMutationType()` ao lado de `getType()`,
  mesmo padrão lazy-por-tabela).

## Fluxo de escrita: create

1. `GqlInputValidator` percorre `getTableFields(cTable)`; para cada campo
   com `X3_OBRIGAT == "S"` ausente no input → erro. Para cada campo
   presente, valida tipo (coerção N/L/D já feita pelo parser de valores
   GraphQL) e `len(valor) <= X3_TAMANHO` para campos `C`.
2. Campo de filial (`GqlDictionaryReader:getFilialField()`) é sempre
   sobrescrito para `cFilAnt`, mesmo que o cliente tenha enviado outro
   valor ou nenhum.
3. `GqlMutationBuilder` monta
   `INSERT INTO <RetSqlName(cTable)> (campos...) VALUES (valores escapados...)`.
4. Após escrita bem-sucedida, `GqlMutationExecutor` extrai os campos de
   chave do input (via `getOrderKey()`) e chama o caminho de leitura
   existente (`GqlExecutor`/`GqlQueryBuilder`, com `cExtraWhere` pela
   chave) para buscar a linha recém-criada e moldá-la pelo selection set.

## Fluxo de escrita: update

1. `getOrderKey(cTable)` separa os campos do input em chave (WHERE) e não-
   chave (SET). Chave ausente no input → erro
   (`"Missing key field '<X>' for update"`).
2. `GqlInputValidator` valida apenas os campos não-chave presentes (mesmas
   regras de tipo/tamanho; obrigatoriedade só se o campo foi enviado —
   update é parcial, campos omitidos não são tocados).
3. Filial forçada a `cFilAnt`, nunca vinda do input, sempre parte do WHERE.
4. `UPDATE <tabela> SET <não-chave = valor,...> WHERE <chave = valor,...>
   AND <filial> AND D_E_L_E_T_ = ' '`.
5. Contagem de linhas afetadas == 0 → erro `"Row not found for update"` (a
   chave não existe, ou existe mas está soft-deletada, ou é de outra
   filial). Nenhuma exceção de banco deveria vazar nesse caminho — a
   ausência de linha é um resultado esperado, não uma falha de SQL.
6. Sucesso → re-seleciona pela chave via `GqlExecutor`, igual ao create.

## Fluxo de escrita: delete

1. `getOrderKey(cTable)` extrai a chave do input; campos não-chave são
   ignorados (delete não os usa).
2. Re-seleciona a linha pela chave **antes** da escrita (via `GqlExecutor`,
   igual aos outros dois fluxos) — é isso que a resposta devolve, já que
   depois do soft-delete a mesma query não encontraria mais a linha sob o
   filtro padrão `D_E_L_E_T_ = ' '`. Se a linha não existe já nessa
   pré-seleção → erro `"Row not found for delete"`, sem tentar o UPDATE.
3. `UPDATE <tabela> SET D_E_L_E_T_ = '*' WHERE <chave = valor,...> AND
   <filial> AND D_E_L_E_T_ = ' '`.

## Validação de input (SX3)

`GqlInputValidator`, um método por regra, todas consultando
`GqlDictionaryReader:getTableFields()` (reaproveita o filtro de campo já
existente — um campo negado por `denyFields`/`X3_VISUAL` nunca é validado
nem aceito, mesmo se vier no input):

- **Obrigatório**: `X3_OBRIGAT == "S"` e ausente no input (create) → erro.
- **Tipo**: valor GraphQL incompatível com `sx3Type` (`N` exige número,
  `L` exige booleano) → erro. Strings sempre aceitas para `C`/`D`/`M`
  (formatação de data fica por conta do cliente, igual à leitura, que já
  serializa `D` como `String`).
- **Tamanho**: para `C`, `len(valor) > X3_TAMANHO` → erro.

Todas as mensagens de erro do input-validator se acumulam num array e são
devolvidas juntas via `GqlErrors:fromArray()` (mesmo padrão do
`GqlValidator` de leitura) — o cliente vê todos os problemas do input numa
única resposta, não um por vez.

## Restrição de acesso

Reaproveita `GqlAccessControl` sem mudança de interface:

1. **Allow-list de mutation** (novo): tabela fora de `allowMutations` →
   nenhum campo `create/update/delete<TABLE>` existe no schema — mesmo
   comportamento de "tabela não gerada" que a deny-list já produz para
   leitura (não aparece em introspecção, e uma tentativa de uso retorna
   `"Unknown or restricted mutation: <name>"`).
2. **Deny-list estrutural** (existente): mesmo com a tabela em
   `allowMutations`, campos em `denyFields`/`X3_VISUAL == "N"` nunca entram
   no `<TABLE>Input` gerado — enviá-los no input é um campo desconhecido do
   tipo, rejeitado pelo `GqlValidator` de argumentos antes mesmo de chegar
   no `GqlMutationExecutor`.
3. **Permissão por usuário** (`GqlAccessControl:allowField` — removido no
   sub-projeto 1 por não ter nenhum chamador; se o sub-projeto de Auth
   precisar de um hook equivalente para mutations, ele é adicionado então,
   não recriado aqui especulativamente).

## Configuração

`custom/backoffice/graphql/config/graphql-config.json` ganha uma chave:

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "allowMutations": [],
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

`allowMutations` é uma lista exata de aliases de tabela (sem wildcard —
liberar escrita é uma decisão por tabela, não um padrão amplo como as
deny-lists de leitura). Vazia por padrão: nenhuma tabela é escrevível até
um administrador adicionar explicitamente.

## Risco técnico a verificar empiricamente no planejamento

O Core Engine usa `TCQuery cSql New Alias &cAlias` (de `topconn.ch`) para
todo `SELECT`. Não está confirmado neste ambiente se o mesmo comando
executa `INSERT`/`UPDATE`, ou se a escrita direta exige uma chamada
diferente (candidato: `TCSqlExec()`). Assim como os gotchas de API do
sub-projeto 1 (`JsonParse` inexistente, `FWExecStatement` inexistente,
etc.), isso será confirmado contra o servidor Protheus/PostgreSQL real
antes de travar o plano de implementação, com o resultado documentado nas
Global Constraints do plano.

## Testes (TIR/Python)

Mesma convenção do sub-projeto 1 (escritos para `tests/tir/`, verificados
via `curl` ao vivo nesta sandbox por falta de `contrib.tir` instalado):

- `test_graphql_mutation_create.tir` — cria um registro em tabela
  liberada, confere retorno moldado pelo selection set e leitura
  subsequente via query.
- `test_graphql_mutation_update.tir` — atualiza campos não-chave,
  confere que campos omitidos permanecem inalterados.
- `test_graphql_mutation_delete.tir` — exclui um registro, confere
  resposta (linha pré-exclusão) e que uma query subsequente não o retorna
  mais (soft-delete).
- `test_graphql_mutation_denylist.tir` — tabela fora de `allowMutations`
  não aparece no schema de mutation e retorna erro claro se invocada.
- `test_graphql_mutation_validation.tir` — input faltando campo
  obrigatório, campo de tipo errado, e campo excedendo `X3_TAMANHO`, cada
  um retornando erro específico sem escrever nada no banco.
- `test_graphql_mutation_notfound.tir` — update/delete com chave
  inexistente (ou soft-deletada, ou de outra filial) retorna
  `"Row not found"` sem lançar exceção de SQL.

## Dependências para sub-projetos seguintes

- **Auth** (sub-projeto 3) pode adicionar um hook de permissão por usuário
  específico para mutations, análogo ao que fará para leitura — a decidir
  no spec daquele sub-projeto, não antecipado aqui.
- **Field Hooks** (sub-projeto 4) pode querer interceptar valores antes da
  escrita (ex: normalizar um campo) — ponto de extensão a decidir naquele
  spec; este spec não cria um hook especulativo agora.
- **SDK Generator** (sub-projeto 5) consome `mutation-schema.tlpp` da mesma
  forma que consome `schema-provider.tlpp` para leitura.
