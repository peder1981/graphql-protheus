# GraphQL SDK Generator - Contratos AdvPL a partir do Schema

Status: implementado e validado ao vivo (unico sub-projeto deste
roteiro sem limitacao de ambiente pendente)
Data: 2026-09-06
Sub-projeto: 5 de 6 (Core Engine -> Mutations -> Auth -> Field Hooks -> **SDK Generator** -> Console PO-UI)

## Contexto

Hoje um consumidor AdvPL deste motor precisa montar a query GraphQL como
string, chamar `/rest/graphql?query=...` via `FWRest`, fazer o parse do
JSON de resposta a mao e ler cada campo por nome de chave (`oJson["A1_COD"]`),
sem tipagem nem checagem em tempo de compilacao. Este sub-projeto gera,
a partir do MESMO dicionario que ja alimenta o schema (SX2/SX3), uma
classe TLPP tipada por tabela - um "contrato" que outro fonte AdvPL pode
copiar para o proprio projeto e usar para ler a resposta de forma
tipada, sem reescrever o mapeamento de campos a mao.

## Objetivo

1. Um novo parametro de query, `?sdk=<TABLE>`, devolve texto-fonte TLPP
   pronto para copiar: uma classe `GqlSdk<TABLE>` com um `data` por
   campo escalar visivel da tabela (mesmo filtro de `denyFields`/
   `X3_VISUAL` que a leitura normal ja usa) e um metodo `fromJson(oRow)`
   que povoa a instancia a partir de um objeto JSON (uma linha da
   resposta de uma query real).
2. Tipo AdvPL de cada `data` vem do mesmo mapeamento SX3->GraphQL que
   `GqlDictionaryReader:mapScalarType()` ja faz, na direcao inversa
   (`Int`/`Float` -> `numeric`, `Boolean` -> `logical`, `String` ->
   `character`).
3. A classe gerada inclui, como comentario Protheus.doc, a query GraphQL
   de exemplo que produz os campos daquele contrato - documentacao viva,
   nao codigo executavel (buscar a query de verdade continua sendo
   responsabilidade do consumidor via `FWRest`, este sub-projeto nao
   gera um cliente HTTP).

Fora de escopo: SDK de mutations (so tipos de leitura por agora), campos
de relacionamento aninhados na classe gerada (`fromJson` so le campos
escalares do proprio nivel - um campo de relacionamento na resposta,
se pedido, e simplesmente ignorado pelo `fromJson`), geracao em lote
(todas as tabelas de uma vez - o parametro e sempre uma tabela por
chamada, o cliente decide quais tabelas precisa), cache do texto gerado
(mesmo custo de reler SX3 que qualquer outra chamada ja tem, sem
otimizacao prematura).

## Decisao de arquitetura

Reaproveitar 100% do `GqlDictionaryReader` existente (mesmos
`getTableFields()`/`getOrderKey()` que a leitura normal usa) - o
gerador SO monta texto a partir dos MESMOS metadados, nunca consulta o
dicionario por conta propria. Isso garante que o SDK gerado nunca diverge
do schema real: um campo bloqueado por `denyFields` nunca aparece no
schema OU no SDK, pelo mesmo motivo (mesma chamada).

## Arquitetura

```
custom/backoffice/graphql/
  core/
    sdk-generator.tlpp -- NOVO: GqlSdkGenerator, monta o texto-fonte
  entrypoints/
    service.entrypoint.tlpp -- + ramo "?sdk=<TABLE>" no despacho existente
```

`GqlSdkGenerator` e injetado no entrypoint do mesmo jeito que
`GqlIntrospection` ja e - um metodo estatico/objeto simples chamado
diretamente, sem estado proprio alem do `oDictionaryReader`.

## Fluxo

```
GET /rest/graphql?sdk=SA1
  -> GqlAccessControl:isTableAllowed("SA1") (mesma checagem estrutural
     de sempre - tabela bloqueada nunca gera SDK, mesmo comportamento de
     "nao existe" que a leitura normal ja tem)
  -> GqlDictionaryReader:getTableFields("SA1")
  -> GqlSdkGenerator:generate("SA1", aFields)
  -> resposta: texto puro (Content-Type text/plain), nao JSON - e codigo
     fonte para copiar, nao dado para o cliente processar
```

Tabela bloqueada ou desconhecida -> mesma resposta de erro que
`?type=<TABLE>` ja devolve hoje para uma tabela invalida (reaproveita
`GqlIntrospection`/`GqlErrors`, sem um formato de erro novo).

## Classe gerada (exemplo, tabela SA1)

```tlpp
#include "tlpp-core.th"

/*/{Protheus.doc}
@type Objeto
@desc GqlSdkSA1 - contrato tipado gerado a partir do schema GraphQL de SA1.
      Query de exemplo: { SA1(limit: 20) { A1_COD A1_NOME A1_END } }
@since gerado automaticamente - nao editar a mao, regerar via
       GET /rest/graphql?sdk=SA1
/@*/
class GqlSdkSA1
    public data A1_COD    as character
    public data A1_NOME   as character
    public data A1_END    as character
    ...

    public method new() as object
    public method fromJson(oRow as json) as object
endclass

method new() as object class GqlSdkSA1
    return self

method fromJson(oRow as json) as object class GqlSdkSA1
    ::A1_COD  := oRow["A1_COD"]
    ::A1_NOME := oRow["A1_NOME"]
    ::A1_END  := oRow["A1_END"]
    ...
    return self
```

Campos numericos/logicos: `fromJson` le o valor cru do JSON (`Int`/
`Float` do GraphQL ja chegam como `N` AdvPL via o parser JSON nativo,
`Boolean` como `L`) - sem coercao extra, o parser JSON do proprio
Protheus (`JsonObject()`) ja entrega o tipo certo.

## Testes (TIR/Python)

Nao depende de nenhuma execucao de AdvPL alem do proprio motor (o texto
gerado nao e compilado nem executado por estes testes - validar isso
seria testar o COMPILADOR AdvPL, fora de escopo):

- `test_graphql_sdk_generates_class_per_table.tir` — `?sdk=SA1` devolve
  texto contendo `class GqlSdkSA1`, um `data` por campo esperado
  (comparado contra a mesma lista que `?type=SA1` ja devolve hoje - os
  dois vem do mesmo `getTableFields()`), e `method fromJson`.
- `test_graphql_sdk_denied_table_errors.tir` — `?sdk=SRA` (tabela
  bloqueada) devolve o mesmo erro que `?type=SRA` ja devolve hoje, nao
  um texto de classe.
- `test_graphql_sdk_unknown_table_errors.tir` — `?sdk=ZZZZZZ` (tabela
  inexistente) devolve erro, nao uma classe vazia.

## Validado ao vivo (implementacao, 2026-09-06)

Ao contrario dos sub-projetos Auth e Field Hooks, este nao depende de
nenhum recurso do ambiente de teste que estivesse faltando ou quebrado -
so texto montado a partir de metadados ja lidos com sucesso pela leitura
normal. `GET /rest/graphql?sdk=SA1` devolveu a classe completa
(`class GqlSdkSA1`, um `data` por campo, `fromJson` correto, tipos
numericos mapeados certos - `A1_COMIS`/`A1_LC`/etc como `numeric`, resto
`character`); `?sdk=SRA` (bloqueada) e `?sdk=ZZZZZZ` (inexistente)
devolveram o mesmo erro que `?type=` ja usa. Unico ajuste de
implementacao sobre o desenhado no spec: a resposta e sempre o mesmo
envelope JSON do resto do motor (`{"data":{"sdk": "<texto>"}}` no
sucesso, `{"errors":[...]}` no erro) em vez de `Content-Type: text/plain`
dedicado - mantem o entrypoint uniforme (sempre chama `oResult:toJson()`
uma unica vez), sem introduzir um segundo formato de resposta so para
este caso.

## Dependencias para sub-projetos seguintes

- **Console PO-UI** (sub-projeto 6) pode expor um botao "baixar SDK" por
  tabela, reaproveitando este endpoint sem mudanca de formato.
