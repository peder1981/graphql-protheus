# GraphQL Protheus — Guia Self-Service

**Versao:** 2.0.0
**Data:** 2026-08-11
**Para:** Desenvolvedores, analistas de dados e consumidores de API do Protheus

---

## 1. Minha Primeira Query

Este guia mostra, passo a passo, como fazer sua primeira consulta GraphQL ao Protheus.

### Pré-requisitos

- Acesso a uma URL do tipo `http://servidor-protheus:porta/`
- Um usuario com permissao de consulta nas tabelas SA1, SB1 ou SC5
- Familiaridade basica com o conceito de GraphQL (opcion al)

### Passo 1 — Acesse o Playground

Abra seu navegador e acesse:

```
http://servidor-protheus:porta/graphql/playground
```

Voce vera uma pagina com:
- Um editor de query no centro (campo de texto grande)
- Um botao **"Executar"** abaixo do editor
- Uma area de resposta abaixo do botao
- Um menu lateral com os tipos disponiveis
- Exemplos de queries prontas para clicar

### Passo 2 — Execute uma query de exemplo

No editor, substitua o conteudo pela query abaixo e clique **"Executar"**:

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

A resposta aparecerá na area inferior:

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

### Passo 3 — Explore outros tipos

No menu lateral, clique em **"Produto"** para ver exemplos de consulta a produtos.
Clique em **"NotaFiscal"** para ver exemplos de consultas a notas fiscais.

### Passo 4 — Use a barra de pesquisa do navegador

Dentro do playground, ha uma area **"Exemplos"** com queries pré-configuradas.
Clique em qualquer um deles para carregá-lo no editor automaticamente.

---

## 2. Como Usar o Playground

### Interface

O playground e dividido em tres areas principais:

```
┌─────────────────────────────────────────────────────────────────┐
│  GraphQL Protheus  │  Protheus 12.1.2510  │  3 modulos | 12 tipos  │
├──────────┬──────────────────────────────────────────────────────┤
│  Tip     │                                                      │
│  • Clie  │  Query                                               │
│  • Prod  │  ┌─────────────────────────────────────────────┐     │
│  • Nota  │  │ { findCliente(codigo: "000001") {           │     │
│          │  │   codigo                                     │     │
│  Modulos │  │   nome                                       │     │
│  • ON Cl │  │ } }                                         │     │
│  • ON Pr │  └─────────────────────────────────────────────┘     │
│  • ON No │                                                      │
│          │  [Executar] [Limpar] [Formatar]                      │
│          │                                                      │
│          │  Resposta                                            │
│          │  ┌─────────────────────────────────────────────┐     │
│          │  │ {                                            │     │
│          │  │   "data": {                                  │     │
│          │  │     "findCliente": {                         │     │
│          │  │       "codigo": "000001",                    │     │
│          │  │       "nome": "Empresa Exemplo",             │     │
│          │  │       "cidade": "SAO PAULO"                  │     │
│          │  │     }                                        │     │
│          │  │   }                                          │     │
│          │  }                                             │     │
│          │  └─────────────────────────────────────────────┘     │
│          │                                                      │
│          │  Exemplos                                            │
│          │  [Cliente - list] [Cliente - find]                   │
│          │  [Produto - list] [Produto - find]                   │
│          └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### Botoes

| Botao | Acao |
|-------|------|
| **Executar** | Envia a query do editor para `/graphql` e mostra a resposta |
| **Limpar** | Limpa o editor e a area de resposta |
| **Formatar** | Tenta indentar a query (basico, sem validacao) |

### Explorando tipos

Clique em um tipo no menu lateral (ex: `Cliente`) para destaca-lo. A area de exemplos mostrara
queries adequadas para aquele tipo.

---

## 3. Como Descobrir o que Está Disponivel

### Metodo 1 — Playground (mais facil)

Acesse `http://servidor/graphql/playground`. O menu lateral mostra todos os tipos registrados.
Os modulos com status `[ON]` estao habilitados e respondendo queries.

### Metodo 2 — Endpoint de modulos (mais detalhado)

```
GET http://servidor/graphql/modules
```

Retorna:

```json
{
  "modules": [
    {
      "key": "customer",
      "table": "SA1",
      "type": "Cliente",
      "enabled": true,
      "fields": ["A1_COD", "A1_NOME", "A1_END", ...],
      "filters": ["A1_NOME", "A1_CIDADE"],
      "fieldCount": 10,
      "discovered": false
    }
  ],
  "config": {
    "defaultFirst": 10,
    "maxFirst": 100,
    "logEnabled": false,
    "autoDiscoverEnabled": true
  },
  "autoDiscover": {
    "tablesDiscovered": 47,
    "tablesSkipped": 11
  }
}
```

### Metodo 3 — Introspeccao GraphQL

GraphQL tem introspeccao nativa. Use qualquer cliente GraphQL (Insomnia, Postman, curl) para
consultar o schema:

```graphql
{
  __schema {
    types {
      name
      fields {
        name
        type { name }
      }
    }
  }
}
```

Ou para ver os campos de um tipo especifico:

```graphql
{
  __type(name: "Cliente") {
    name
    fields {
      name
      type { name }
      args {
        name
        type { name }
      }
    }
  }
}
```

### Metodo 4 — Endpoint de schema expandido

```
GET http://servidor/graphql/schema
```

Retorna o schema completo em JSON, incluindo todos os tipos, campos e argumentos.

---

## 4. Como Montar Queries com Filtros e Paginacao

### Query de busca por codigo (find)

Use `find{Tipo}` para buscar um registro unico por sua chave primaria:

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

A chave primaria e sempre o **primeiro campo** definido no modulo. Para SA1, e `A1_COD`.

### Query de lista com filtros (list)

Use `list{Tipo}` para buscar multiplos registros. Filtros disponiveis sao os campos listados
em `module.<nome>.filter` no `appserver.ini`.

```graphql
{
  listCliente(primeiro: 10, offset: 0, nome: "EMPRESA", cidade: "SAO PAULO") {
    codigo
    nome
    cidade
  }
}
```

### Paginacao

Parametros de paginacao:

| Parametro | Tipo | Padrao | Descricao |
|-----------|------|--------|-----------|
| `primeiro` | Int | 10 | Maximo de registros a retornar |
| `offset` | Int | 0 | Quantidade de registros a pular |

**Paginacao ordinal (recomendada):**

```graphql
# Pagina 1 — primeiros 10
{ listCliente(primeiro: 10, offset: 0) { codigo nome } }

# Pagina 2 — proximos 10
{ listCliente(primeiro: 10, offset: 10) { codigo nome } }

# Pagina 3 — proximos 10
{ listCliente(primeiro: 10, offset: 20) { codigo nome } }
```

**Limite maximo:** o valor de `primeiro` nao pode exceder `default.maxFirst` (padrao: 100).
Tente paginares com `primeiro: 50` para trazer mais registros de uma vez.

### Filtrando por campos

Os campos filtraveis sao configurados individualmente por modulo. Para saber quais campos
podem ser usados como filtro:

1. Acesse `/graphql/modules` e verifique o array `filters` de cada modulo
2. Ou use introspeccao:
   ```graphql
   {
     __type(name: "Cliente") {
       name
       fields {
         name
         type { name }
       }
     }
   }
   ```

### Exemplos combinados

**Buscar clientes de SP com nome contendo "LTD":**

```graphql
{
  listCliente(primeiro: 20, offset: 0, nome: "LTD", estado: "SP") {
    codigo
    nome
    cidade
    estado
  }
}
```

**Listar todas as notas fiscais de um cliente em um periodo:**

```graphql
{
  listNotaFiscal(primeiro: 20, offset: 0, cliente: "000001", dataIni: "2024-01-01", dataFim: "2024-12-31") {
    numero
    emissao
    serie
    cliente
  }
}
```

**Buscar produto por descricao:**

```graphql
{
  listProduto(primeiro: 10, offset: 0, palavra: "PARAFUSO") {
    codigo
    descricao
    unidademedida
    localizacao
  }
}
```

---

## 5. FAQ

### "Quais tabelas posso consultar?"

Tabelas expostas dependem da configuracao do `appserver.ini` no servidor. Para ver quais estao
disponiveis:

```
GET http://servidor/graphql/modules
```

Ou acesse o playground em `http://servidor/graphql/playground` e olhe o menu lateral.

Atualmente os modulos padrao incluem:

| Modulo | Tabela | Tipo GraphQL |
|--------|--------|-------------|
| customer | SA1 | Cliente |
| product | SB1 | Produto |
| invoice | SC5 | NotaFiscal |

Com auto-discovery habilitado, novas tabelas podem aparecer automaticamente.

---

### "Como vejo todos os campos de uma tabela?"

**Metodo 1 — Introspeccao:**

```graphql
{
  __type(name: "Cliente") {
    name
    fields {
      name
      type { name }
    }
  }
}
```

**Metodo 2 — Query direta:**

```graphql
{
  findCliente(codigo: "000001") {
    __typename
    codigo
    nome
    endereco
    bairro
    cidade
    estado
    telefone
    tipo
    inscricaoEstadual
    cgc
  }
}
```

**Metodo 3 — Endpoint de modulos:**

```
GET /graphql/modules
```

O campo `fields` de cada modulo lista todos os campos expostos.

---

### "Posso filtrar por qualquer campo?"

Nao. Somente os campos listados na chave `module.<nome>.filter` do `appserver.ini` sao
filtraveis. Campos nao listados podem ser selecionados na query (se estiverem no schema),
mas nao podem ser usados como argumento de filtro.

Para ver os filtros disponiveis de um modulo:

```json
// Resultado de /graphql/modules
{
  "modules": [
    {
      "key": "customer",
      "table": "SA1",
      "filters": ["A1_NOME", "A1_CIDADE", "A1_ESTADO", "A1_TIPO"]
    }
  ]
}
```

Neste exemplo, voce pode filtrar por `nome`, `cidade`, `estado` e `tipo`, mas nao por
`endereco` ou `telefone`.

---

### "Por que recebo null para um campo?"

Os motivos mais comuns:

1. **Soft-delete (D_E_L_E_T_):** O registro foi marcado como deletado no Protheus.
   O GraphQL filtra automaticamente `D_E_L_E_T_ = ' '`, entao o registro simplesmente
   nao aparecera na lista. Se voce espera ver um registro, verifique no Protheus se ele
   esta ativo.

2. **Filial incorreta:** A query esta sendo executada em uma filial diferente da que contem
   os dados. Use o parametro `filial` na URL ou defina `MV_GQLFIL` no appserver.ini.

3. **Campo nao preenchido:** O campo e valido no schema, mas o registro nao tem valor
   preenchido. Isso e normal — o Protheus permite campos nulos.

4. **Campo nao mapeado:** O campo existe na tabela mas nao foi incluído na lista
   `module.<nome>.fields` do appserver.ini.

**Como diagnosticar:**

```graphql
# Teste com uma query que seleciona o campo-chave para verificar se o registro existe
{
  findCliente(codigo: "000001") {
    codigo
    nome
  }
}
```

Se `findCliente` retorna `null`, o registro nao existe naquela filial ou foi soft-deletado.

---

### "Como adiciono uma tabela que não está na lista?"

Voce precisa de acesso ao `appserver.ini` do servidor Protheus. Siga estes passos:

**Passo 1** — Edite o `appserver.ini` e adicione na secao `[GraphQL]`:

```ini
module.minhamodela.table   = SXX
module.minhamodela.type    = MeuTipo
module.minhamodela.fields  = X9_COD,X9_DESC,X9_TIPO
module.minhamodela.filter  = X9_DESC
module.minhamodela.enabled = 1
```

**Passo 2** — Reinicie o appserver:

```bash
net stop "TOTVS Application Server"
net start "TOTVS Application Server"
```

**Passo 3** — Verifique se o modulo foi carregado:

```
GET http://servidor/graphql/modules
```

Voce deve ver seu modulo na lista com `enabled: true`.

**Passo 4** — Teste uma query:

```graphql
{
  listMeuTipo(primeiro: 10, offset: 0) {
    x9Cod
    x9Desc
    x9Tipo
  }
}
```

**Opcao alternativa — Auto-discovery:**

Se voce nao quiser listar os campos manualmente, deixe `fields` vazio e habilite o
auto-discovery:

```ini
module.autoDiscover.enabled      = 1
module.autoDiscover.minFields    = 3

module.minhamodela.table   = SXX
module.minhamodela.type    = MeuTipo
module.minhamodela.fields  =
module.minhamodela.enabled = 1
```

O sistema ira buscar automaticamente os campos da tabela no dicionario SX3.

---

## 6. Troubleshooting para Consumidores

### Erro: "Unknown field 'X' on type 'Y'"

**Causa:** O campo especificado nao existe no schema GraphQL do tipo informado.

**Solucao:**
1. Verifique o nome do campo usando introspeccao:
   ```graphql
   { __type(name: "Cliente") { fields { name } } }
   ```
2. Campos Protheus usam camelCase no GraphQL (ex: `A1_COD` → `a1Cod` ou `codigo`, dependendo do mapeamento).
3. Consulte `docs/api-reference.md` para a tabela de mapeamento completa.

---

### Erro: "Unknown type 'X'"

**Causa:** O tipo informado nao foi registrado no schema.

**Solucao:**
1. Verifique se o modulo esta habilitado em `/graphql/modules`
2. Verifique se o modulo foi configurado no `appserver.ini`
3. Confirme se o appserver foi reiniciado apos a configuracao

---

### Erro: Parse error

**Causa:** A query tem sintaxe invalida.

**Solucoes comuns:**

| Erro | Causa | Correcao |
|------|-------|----------|
| `Expected name but found` | Falta dois pontos em argumentos | `codigo:"001"` → `codigo: "001"` |
| `Unexpected token` | Chave `{` desbalanceada | Verifique se todo `{` tem `}` correspondente |
| `Unknown argument` | Argumento com nome errado | Verifique nomes no schema |
| `Unterminated string` | String sem aspas de fechamento | `codigo: "001` → `codigo: "001"` |

**Dica:** Use o botao **"Formatar"** no playground para tentar corrigir a indentacao.

---

### Query retorna array vazio `[]`

**Possiveis causas:**

1. **Nenhum registro corresponde aos filtros** — use filtros mais amplos ou remova-os.
2. **Filial incorreta** — verifique se a filial passada corresponde aos dados.
3. **Soft-delete** — os registros existem mas estao marcados como deletados.
4. **Paginacao com offset grande** — o offset ultrapassa o total de registros.

**Diagnostico rapido:**

```graphql
# Query sem filtros, pagina 1
{
  listCliente(primeiro: 10, offset: 0) {
    codigo
    nome
  }
}
```

Se retornar dados, o problema e nos filtros. Se retornar vazio, verifique a filial.

---

### Erro 404 em `/graphql`

**Causa:** O endpoint nao esta configurado no appserver.

**Solucao:** Verifique se o `appserver.ini` contem:

```ini
[REST]
/graphql = custom.backoffice.graphql.service.entrypoint
```

Se a linha nao existir, adicione e reinicie o appserver.

---

### Erro: "Execution error" ou timeout

**Causas possiveis:**

1. **Query muito complexa** — reduza o numero de campos ou o `primeiro`.
2. **Conexao instavel** — verifique a rede entre o consumidor e o appserver.
3. **Servidor sobrecarregado** — consulte o administrador do Protheus.

**Diagnostico:** Teste com uma query minima:

```graphql
{
  findCliente(codigo: "000001") {
    codigo
  }
}
```

Se funcionar, o problema e na complexidade da query original.

---

### Campos retornam string vazia `""`

Isso e normal para campos que nao tem valor preenchido no Protheus. O GraphQL Protheus
mapeia todos os campos como `String`, incluindo campos numericos e datas. Um campo vazio
no banco sera retornado como `""`.

Para campos numéricos, converta no lado do consumidor:
```javascript
const quantidade = parseInt(response.data.findProduto.quantidade) || 0;
```

---

## 7. Dicas Rapidas

| Tarefa | Comandos |
|--------|----------|
| Ver modulos disponiveis | `GET /graphql/modules` |
| Ver schema completo | `GET /graphql/schema` |
| Abrir playground | `GET /graphql/playground` |
| Query de teste rapida | `curl "http://servidor/graphql?query={findCliente(codigo:\"000001\"){codigo nome}}"` |
| Query com filial | Adicione `&filial=01` na URL |
| Paginacao | `listCliente(primeiro: 20, offset: 0)` |
| Filtro | `listCliente(primeiro: 10, offset: 0, cidade: "SAO PAULO")` |

---

*Este guia faz parte do projeto GraphQL Protheus v2.0.0. Para detalhes tecnicos, consulte
`docs/architecture.md`. Para referencia completa da API, consulte `docs/api-reference.md`.*
