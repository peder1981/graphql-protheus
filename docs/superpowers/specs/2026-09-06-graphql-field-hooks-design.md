# GraphQL Field Hooks — Pontos de Extensao por Campo

Status: aprovado para planejamento
Data: 2026-09-06
Sub-projeto: 4 de 6 (Core Engine -> Mutations -> Auth -> **Field Hooks** -> SDK Generator -> Console PO-UI)

## Contexto

Os tres sub-projetos anteriores (leitura, mutations, auth) cobrem o motor
generico dicionario-orientado. Nenhum deles permite que um desenvolvedor
Protheus rode LOGICA DE NEGOCIO customizada por campo — nem para
transformar um valor lido (ex.: mascarar, formatar, derivar) nem para
normalizar/validar um valor antes de gravar (ex.: default, trim, regra
especifica de uma tabela). Este sub-projeto adiciona exatamente isso, sem
tocar em nenhum outro comportamento existente.

## Objetivo

1. Um desenvolvedor registra, via config (`fieldHooks` em
   `graphql-config.json`), o nome de uma `User Function` AdvPL/TLPP a
   rodar para um campo especifico de uma tabela, em um destes dois
   pontos: `onRead` (depois de ler o valor do banco, antes de montar a
   linha de resposta) ou `onWrite` (depois da validacao do
   `GqlInputValidator`, antes do `FieldPut` em create/update).
2. A funcao recebe o valor bruto e devolve o valor transformado — mesma
   assinatura nos dois casos: `Function U_MeuHook(uValor) as variant`.
3. Hook ausente/nao configurado para um campo -> comportamento identico
   a hoje (sem overhead, sem chamada nenhuma).
4. Falha ao resolver ou executar um hook (funcao nao existe, erro em
   runtime) nunca derruba a requisicao inteira — loga e segue com o
   valor original, tanto em leitura quanto em escrita. Motivo: um bug em
   hook de terceiro nao deveria transformar uma leitura/escrita valida
   em erro 500 - o pior caso aceitavel e o hook simplesmente nao rodar.

Fora de escopo: hooks multi-campo (que leem/alteram outros campos da
mesma linha), hooks assincronos, hooks que abortam a operacao (ex.:
"hook de validacao que rejeita a escrita") - isso e responsabilidade do
`GqlInputValidator` (sub-projeto 2) ou de um `oInputValidator` mais rico
numa fase futura, nao deste sub-projeto. Hooks tambem nao veem o usuario
autenticado nesta fase (isso ficaria doc como TODO para quando
`authEnforced` estiver validado de ponta a ponta, ver spec do Auth).

## Decisao de arquitetura

Resolucao dinamica de funcao via macro AdvPL (`&("{|u| " + cFunc + "(u)}")`
compilado uma vez por chamada, tecnica padrao AdvPL para chamar por nome
de string) — reaproveita o interpretador nativo em vez de qualquer
registry/dispatch customizado. `cFunc` vem sempre da config
(`fieldHooks`), nunca de input do cliente HTTP — sem risco de injecao de
codigo via requisicao.

## Arquitetura

```
custom/backoffice/graphql/
  core/
    field-hooks.tlpp   -- NOVO: GqlFieldHooks, resolve e chama hooks
                          onRead/onWrite por "TABELA.CAMPO"
  config/
    graphql-config.json -- + "fieldHooks": {
                              "SA1.A1_NOME": { "onRead": "U_HookX", "onWrite": "U_HookY" }
                            }
```

`GqlFieldHooks` e injetado em `GqlExecutor` (chamado em
`resolveTableField()`, ao montar cada campo escalar da linha) e em
`GqlWorkareaWriter` (chamado em `writeCreate()`/`writeUpdate()`, logo
antes de cada `FieldPut`).

## Fluxo de leitura

Em `resolveTableField()`, para cada campo escalar da selecao, depois de
`FieldGet()` e antes de guardar em `oRow[...]`:

```
uValor := FieldGet(FieldPos(cCampo))
uValor := ::oFieldHooks:applyRead(cTable, cCampo, uValor)
oRow[cAlias] := uValor
```

## Fluxo de escrita

Em `writeCreate()`/`writeUpdate()` (`workarea-writer.tlpp`), para cada
campo presente no input, depois da validacao (`GqlInputValidator` ja
rodou antes de chegar aqui) e antes do `FieldPut`:

```
uValor := ::oFieldHooks:applyWrite(cTable, cCampo, uValor)
FieldPut(FieldPos(cCampo), uValor)
```

## `GqlFieldHooks`

```
class GqlFieldHooks
    private data oConfig as object

    public method new(oConfig as object) as object
    public method applyRead(cTable as character, cField as character, uValue as variant) as variant
    public method applyWrite(cTable as character, cField as character, uValue as variant) as variant
    method resolveHook(cTable as character, cField as character, cDirection as character) as character
    method callHook(cFuncName as character, uValue as variant) as variant
endclass
```

- `resolveHook()`: monta a chave `"TABELA.CAMPO"`, busca em
  `oConfig:getFieldHooks()` (novo getter, mesmo padrao json de
  `getGroupPermissions()`), devolve o nome da funcao para `onRead`/
  `onWrite` ou `""` se nao configurado.
- `callHook()`: `begin sequence ... recover using oErr` em torno da
  chamada macro-compilada; recover loga via `FWLogMsg()` e devolve
  `uValue` original sem transformar. Nao usa `ExistBlock()`/`Type()` em
  loop (proibido pelas convencoes do projeto) - a checagem de existencia
  da funcao e feita pelo proprio erro de compilacao do bloco, capturado
  no `recover`.

## Configuracao

```json
{
  "fieldHooks": {
    "SA1.A1_NOME": { "onRead": "U_GqlUpperName" }
  }
}
```

Chave `"TABELA.CAMPO"` (nao dois niveis de objeto) por simplicidade de
implementacao e leitura - `GqlConfig` so precisa de um `JsonObject` plano,
sem iteracao aninhada. Ausente do mapa -> sem hook, custo zero (nem chega
a montar a chave de busca se `oConfig:getFieldHooks()` devolver um objeto
vazio, checado uma vez por chamada de `resolveHook()`).

## Testes (TIR/Python)

Dependem de uma `User Function` de teste real compilada no ambiente
(ex.: `U_GqlHookUpper(cValor) return upper(cValor)`), adicionada como
fonte de teste deste sub-projeto:

- `test_graphql_fieldhook_read_transforms_value.tir` — campo com
  `onRead` configurado devolve o valor transformado, outro campo da
  mesma linha sem hook devolve o valor original.
- `test_graphql_fieldhook_write_transforms_value.tir` — mutation
  `create` com `onWrite` configurado grava o valor ja transformado
  (confirmado por uma leitura subsequente).
- `test_graphql_fieldhook_missing_function_degrades.tir` — hook
  configurado apontando para uma funcao que nao existe: a requisicao
  ainda devolve `200`/`data`, com o valor original, sem erro 500.

## Dependencias para sub-projetos seguintes

- **SDK Generator** (sub-projeto 5) nao precisa saber de hooks - eles
  sao transparentes no schema (o campo continua tendo o mesmo tipo
  GraphQL, so o valor muda).
- **Console PO-UI** (sub-projeto 6) provavelmente expoe `fieldHooks`
  como tela de administracao, igual a `groupPermissions` do Auth - este
  spec so define o formato JSON.
