# Manual de Utilização

Referência completa da API GraphQL exposta por este motor. Público-alvo:
desenvolvedores que vão consumir o serviço a partir de outro sistema,
integração ou aplicação.

## Endpoint

Todo o acesso é feito por um único endpoint REST:

```
GET /rest/graphql
```

| Uso | Exemplo |
|---|---|
| Listar tipos disponíveis (introspecção) | `GET /rest/graphql` |
| Ver os campos de uma tabela | `GET /rest/graphql?type=SA1` |
| Executar uma consulta ou mutation | `GET /rest/graphql?query=<texto GraphQL codificado na URL>` |

O texto GraphQL vai sempre no parâmetro `query`, url-encoded. Os
exemplos abaixo mostram o texto GraphQL "cru" — para usá-lo via `curl`,
codifique-o (`urllib.parse.quote_plus` em Python, ou qualquer codificador
de query string).

## Introspecção

### Listar tabelas disponíveis

```bash
curl "http://localhost:9995/rest/graphql"
```

```json
{"data":{"__schema":{"queryType":{"name":"Query"},"types":[{"name":"SA1"},{"name":"SA2"}, ...]}}}
```

Só aparecem tabelas **não** bloqueadas pela configuração do servidor —
tabelas bloqueadas nunca aparecem aqui, independentemente de você saber
o nome delas.

### Ver os campos de uma tabela

```bash
curl "http://localhost:9995/rest/graphql?type=SA1"
```

```json
{"data":{"__type":{"name":"SA1","fields":[
  {"name":"A1_COD","sx3Type":"C","graphqlType":"String","maxLength":6,"required":false},
  {"name":"A1_NOME","sx3Type":"C","graphqlType":"String","maxLength":50,"required":false},
  ...
],"relations":[
  {"name":"SC5","type":"[SC5]","cardinality":"MANY"}
]}}}
```

Cada campo traz: nome real, tipo AdvPL/SX3 original, tipo GraphQL
mapeado, tamanho máximo e se é obrigatório. Campos bloqueados por
configuração ou marcados como não-visíveis no dicionário (`X3_VISUAL =
"N"`) nunca aparecem aqui.

## Consultas (queries)

### Sintaxe básica

```graphql
{ SA1(limit: 5) {
    A1_COD
    A1_NOME
} }
```

Retorna até 5 registros de `SA1`, trazendo apenas os campos pedidos.

### Paginação

Toda listagem aceita `limit` e `offset`:

```graphql
{ SA1(limit: 20, offset: 40) {
    A1_COD
} }
```

- `limit` — sem informar, usa o padrão configurado (`defaultPageSize`).
  Sempre limitado ao teto do servidor (`maxPageSize`), mesmo que você
  peça mais.
- `offset` — sem informar, começa do início (`0`).

### Filtros

```graphql
{ SA1(filter: [{field: "A1_COD", op: "eq", value: "000001"}]) {
    A1_COD
    A1_NOME
} }
```

Operadores suportados: `eq` (igual), `gt` (maior que), `gte` (maior ou
igual), `lt` (menor que), `lte` (menor ou igual). Vários filtros no
mesmo array são combinados com `AND`:

```graphql
{ SA1(filter: [
    {field: "A1_COD", op: "gte", value: "000100"},
    {field: "A1_COD", op: "lt", value: "000200"}
  ]) {
    A1_COD
} }
```

Todo valor de filtro é escapado automaticamente antes de chegar ao
banco — não há risco de injeção de SQL via filtro.

### Campos de relacionamento (aninhamento)

Relacionamentos declarados no dicionário do Protheus (SX9) aparecem
como campos aninhados, resolvidos automaticamente:

```graphql
{ SA1(limit: 5) {
    A1_COD
    A1_NOME
    SC5 { C5_NUM C5_EMISSAO }
} }
```

Isso traz, para cada cliente, os pedidos de venda relacionados (via a
regra de vínculo do SX9 entre `SA1` e `SC5`). Relacionamentos podem ser
1:1 ou 1:N (lista) — o tipo de retorno já reflete isso na introspecção
(`"type":"[SC5]"` para 1:N, `"type":"SC5"` para 1:1). Não há limite de
profundidade de aninhamento imposto pelo servidor.

### Apelidos (aliases)

Para pedir a mesma tabela mais de uma vez na mesma consulta, com
critérios diferentes, use apelidos:

```graphql
{
  recentes: SA1(limit: 5, filter: [{field: "A1_COD", op: "gte", value: "000900"}]) { A1_COD }
  antigos: SA1(limit: 5, filter: [{field: "A1_COD", op: "lt", value: "000100"}]) { A1_COD }
}
```

A resposta traz cada resultado sob a chave do apelido, não do nome da
tabela.

## Mutations (escrita)

Mutations só existem para tabelas explicitamente liberadas pelo
administrador do servidor (veja `manual-implementacao.md`). Tentar uma
mutation em tabela não liberada retorna erro claro, não um erro de
servidor.

**Toda mutation precisa começar com a palavra-chave `mutation`** — sem
ela, o texto é interpretado como consulta de leitura comum.

### Criar um registro

```graphql
mutation { createSA1(input: {A1_COD: "000123", A1_LOJA: "01", A1_NOME: "Cliente Novo"}) {
    A1_COD
    A1_NOME
} }
```

O campo de filial nunca precisa (e não deve) ser enviado em `create` —
o servidor sempre usa a filial da sessão atual, ignorando qualquer valor
enviado pelo cliente nesse campo.

A resposta traz o registro recém-criado, moldado exatamente pelos campos
pedidos na seleção — igual a uma consulta normal.

### Atualizar um registro

```graphql
mutation { updateSA1(input: {A1_FILIAL: "01", A1_COD: "000123", A1_LOJA: "01", A1_NOME: "Nome Atualizado"}) {
    A1_NOME
} }
```

**Update é sempre parcial**: envie no `input` os campos de chave
(obrigatórios, para identificar a linha) mais **somente** os campos que
você quer alterar. Campos omitidos permanecem com o valor atual,
inalterados.

Os campos de chave dependem do índice de ordem 1 real da tabela no
Protheus — para `SA1`, são `A1_FILIAL`, `A1_COD` e `A1_LOJA`. Se algum
campo de chave estiver faltando no `input`, a mutation retorna erro
explícito (`"Missing key field '<campo>' for update"`) em vez de
adivinhar.

Se a chave não corresponder a nenhum registro ativo, a resposta é:

```json
{"errors":[{"message":"Row not found for update"}]}
```

### Excluir um registro

```graphql
mutation { deleteSA1(input: {A1_FILIAL: "01", A1_COD: "000123", A1_LOJA: "01"}) {
    A1_COD
} }
```

A exclusão é sempre lógica (soft-delete) — o registro deixa de aparecer
em consultas normais, mas o dado físico permanece, exatamente como
qualquer outra exclusão no Protheus. A resposta traz os dados do
registro **antes** da exclusão, moldados pela seleção pedida.

Assim como em `update`, uma chave que não corresponde a nenhum registro
ativo retorna `"Row not found for delete"` em vez de um erro genérico.

## Formato de erros

Toda falha — de validação, de execução, ou de acesso negado — segue o
mesmo formato, compatível com o padrão GraphQL:

```json
{"errors":[{"message":"descrição do problema"}]}
```

Múltiplos problemas do mesmo request (por exemplo, vários campos
inválidos numa mutation) podem vir juntos na mesma lista `errors`.

### Erros comuns e o que significam

| Mensagem | Causa |
|---|---|
| `Unknown or restricted table: '<nome>'` | Tabela não existe, está bloqueada, ou você esqueceu a palavra `mutation` numa chamada de escrita |
| `Unknown or restricted mutation: <nome>` | Tabela existe para leitura, mas não está liberada em `allowMutations` |
| `Mutation '<nome>' requires an 'input' argument` | A chamada não incluiu o argumento `input` |
| `Mutation '<nome>' argument 'input' must be an object` | `input` foi enviado como algo que não é um objeto (ex. um número ou string solto) |
| `Field '<campo>' is required` | Campo obrigatório (SX3) ausente no `input` de um `create` |
| `Field '<campo>' must be a string` / `must be numeric` / `must be boolean` | Tipo do valor enviado não bate com o tipo real do campo |
| `Field '<campo>' exceeds max length <N>` | Valor de texto maior que o tamanho máximo do campo (`X3_TAMANHO`) |
| `Missing key field '<campo>' for update` / `for delete` | Faltou um campo de chave no `input` de `update`/`delete` |
| `Update requires at least one non-key field` | O `input` de um `update` só trouxe campos de chave, nada para alterar |
| `Row not found for update` / `for delete` | A chave enviada não corresponde a nenhum registro ativo |
| `Write failed for '<mutation>'` | A escrita no banco falhou (SQL malformado, colisão de chave, etc.) |

## Coisas que a API intencionalmente não faz (ainda)

- **Não gera chave automaticamente**: você sempre informa o valor de
  `A1_COD` (ou equivalente) no `create` — não há numeração automática via
  SX5.
- **Não roda validações de negócio do Protheus**: apenas obrigatoriedade,
  tipo e tamanho (do SX3) são verificados. Regras de rotina, triggers e
  fórmulas de validação do cadastro padrão não são executadas.
- **Não faz mutations em lote**: cada chamada de `create`/`update`/
  `delete` afeta um único registro.
- **Não tem autenticação por usuário ainda**: o controle de acesso atual
  é só por configuração de servidor (tabelas/campos bloqueados). Isso
  está previsto para um sub-projeto futuro (Auth).

Veja `manual-implementacao.md` para as limitações operacionais
(concorrência em `create`, dependência do índice SIX) que quem consome a
API deve conhecer antes de depender dela em produção.
