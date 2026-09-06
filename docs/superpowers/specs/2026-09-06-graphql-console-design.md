# GraphQL Console - Interface de Administracao/Exploracao

Status: implementado e validado ao vivo no navegador
Data: 2026-09-06
Sub-projeto: 6 de 6 (Core Engine -> Mutations -> Auth -> Field Hooks -> SDK Generator -> **Console**)

## Decisao de escopo (mudanca sobre o nome original do roteiro)

O roteiro original (specs dos sub-projetos 1-5) chamava este ultimo item
de "Console PO-UI", nome que aponta para o design system Angular da
TOTVS (@po-ui/ng-components). Decisao tomada com o operador antes deste
spec: construir uma pagina HTML/CSS/JS estatica, sem framework, em vez
de um app Angular completo com PO-UI de verdade. Motivo: a
funcionalidade real que um "console de administracao/exploracao" precisa
- rodar query, navegar tabelas, baixar SDK - nao depende de nenhum
recurso especifico do PO-UI, e um app Angular exigiria uma stack de
build inteira nova (npm, Angular CLI, @po-ui/ng-components) para uma
entrega ordens de magnitude maior sem ganho funcional proporcional. A
pagina reaproveita 100% os endpoints REST que os sub-projetos 1, 5 e o
proprio motor de leitura ja expoem, sem nenhum endpoint novo no lado do
Protheus.

## Objetivo

Uma pagina unica (`console/index.html`, sem build, abrir direto no
navegador ou servir por qualquer servidor estatico) com:

1. Campo para a URL base do endpoint GraphQL (persistida em
   localStorage) e botao "Conectar".
2. Console de query: textarea + botao "Executar", resultado formatado
   como JSON.
3. Navegador de tabelas via introspeccao (`GET ?` para nomes, `GET
   ?type=<TABLE>` para campos) - com filtro de texto, nunca lista tudo
   de uma vez (ver "Achado ao vivo" abaixo).
4. Botao "Baixar SDK" por tabela selecionada, usando `GET ?sdk=<TABLE>`
   (sub-projeto 5) para baixar o `.tlpp` gerado.

Fora de escopo: autenticacao da propria pagina (ela chama o endpoint
como qualquer cliente HTTP - se `authEnforced`/`Security=1` estiverem
ligados no backend, o navegador pede Basic Auth nativamente, sem
codigo adicional na pagina), edicao de `groupPermissions`/`fieldHooks`
pela UI (so leitura/exploracao nesta fase), mutations pela UI (o console
de query aceita qualquer query GraphQL, incluindo mutation, mas nao ha
formulario dedicado para montar uma).

## Achado ao vivo: schema com 10.409 tabelas trava o navegador

Confirmado ao vivo contra o servidor real deste projeto: o schema
completo (`GET /rest/graphql`) lista **10.409 tipos**. A primeira versao
da pagina renderizava uma `<div>` com listener de clique por tabela -
isso travou o Chrome de verdade (timeout de 30s+ em `Page.captureScreenshot`,
reproduzido de forma consistente). Corrigido: a lista de tabelas nunca
renderiza mais que `MAX_RENDERED_TABLES` (200) nós de uma vez - sem
filtro, mostra as primeiras 200; com filtro, mostra so as que baterem
(ate o mesmo teto), com uma contagem total sempre visivel. Isso nao e
uma limitacao deste ambiente de teste especificamente - um dicionario
Protheus real tem exatamente essa ordem de grandeza de tabelas, entao
qualquer implementacao futura de uma tela de administracao real
(inclusive uma eventual reescrita em Angular/PO-UI) precisa da mesma
cautela: nunca renderizar uma lista de tabelas sem paginacao/filtro.

## Validado ao vivo (via Claude-in-Chrome, navegador real)

- Conexao e listagem inicial: 200 tabelas mostradas, contagem correta
  (10.409 no schema).
- Filtro por texto: reduz a lista corretamente (testado com "SA1" ->
  1 resultado).
- Selecao de tabela: aba "Campos da tabela" populada corretamente (260
  linhas de header+campos para SA1), query de exemplo preenchida
  automaticamente com os 5 primeiros campos.
- Execucao de query: resultado real da tabela SA1 renderizado como JSON
  formatado.
- Botao de SDK: endpoint `?sdk=SA1` confirmado acessivel e retornando o
  texto-fonte esperado (mesmo endpoint do sub-projeto 5, sem mudanca).

Achado adicional, nao relacionado ao codigo da pagina: a primeira versao
do `<textarea>` de query usava `placeholder` para mostrar o exemplo em
vez de um `value` real - um clique em "Executar" sem digitar nada mandava
`query=""` para o servidor, que (por nao ser tratado como "sem query")
caia no ramo de `schemaNames()` do entrypoint em vez de mostrar um erro
claro. Corrigido dando ao `<textarea>` um `value` real (nao so
`placeholder`). Nao mudou nada no lado do Protheus - o comportamento do
entrypoint para `query=""` continua o mesmo de antes deste sub-projeto.

## Dependencias para sub-projetos seguintes

Nenhuma - este e o ultimo sub-projeto do roteiro original de 6.
