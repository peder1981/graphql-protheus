# GraphQL Auth — Autenticação e Autorização por Usuário

Status: aprovado para planejamento
Data: 2026-09-06
Sub-projeto: 3 de 6 (Core Engine → Mutations → **Auth** → Field Hooks → SDK Generator → Console PO-UI)

## Contexto

Hoje o endpoint `/rest/graphql` não exige autenticação nenhuma: o
`appserver.ini` dos containers de teste (`protheus`, `protheus-graphql`)
está com `[HTTPREST] Security=0` (confirmado ao vivo,
`docker exec protheus-compile cat .../appserver.ini`). `GqlAccessControl`
já documenta esse gap no próprio cabeçalho Protheus.doc desde o
sub-projeto 1: só existe a lista de bloqueio estrutural (tabela/campo),
nenhuma verificação de quem está chamando.

Este spec cobre exclusivamente autenticação (quem é o usuário) e
autorização por usuário (o que esse usuário pode ler/escrever), tanto para
queries quanto para mutations. SDK, console PO-UI e hooks de campo
continuam fora de escopo.

**Decisão de arquitetura:** reaproveitar a autenticação nativa do
Protheus (`Security=1` no `[HTTPREST]`, Basic Auth contra usuário RM real)
em vez de um esquema próprio (token/JWT customizado). Motivo: é o mesmo
mecanismo que os endpoints oficiais `/api/framework/v1/*` já usam
(confirmado via documentação indexada), testado pela própria TOTVS, sem
superfície nova para manter. Custo aceito: liga autenticação para
**todos** os REST endpoints do appserver, não só o GraphQL — decisão
tomada com o operador antes deste spec, dado o impacto compartilhado.

## Objetivo

1. Toda chamada a `/rest/graphql` exige Basic Auth válida contra um
   usuário Protheus real (`Security=1`).
2. `GqlAccessControl` ganha uma terceira camada de verificação, por
   usuário, além da deny-list estrutural (tabela/campo) e da allow-list de
   mutation já existentes — as três se combinam, nenhuma isolada é
   suficiente.
3. Autorização por usuário é por **grupo Protheus** (SU quando aplicável,
   ou o grupo do usuário retornado por `GetUserId()`/`RetCodUsr()`), não
   por usuário individual — evita uma lista de exceções por pessoa.
4. Erro de autorização (usuário autenticado mas sem permissão) é
   distinguível de erro de autenticação (sem credencial/credencial
   inválida): o segundo nunca chega ao código GraphQL — é o próprio
   `Security=1` do Protheus que responde `401` antes do `GQLSERVICE` ser
   chamado.

Fora de escopo: SSO/OAuth2/TOTVS Identity, gestão de usuários via REST
(criação/senha — já existe API oficial, não reimplementada aqui), cache de
permissão entre requisições (cada requisição relê o grupo do usuário —
sem otimização prematura), permissão por campo diferenciada por grupo
(fica por tabela/operação inteira nesta fase).

## Não-objetivos / decisões explícitas

- **Sem esquema de auth próprio.** Ver "Decisão de arquitetura" acima.
- **Sem permissão por usuário individual.** Só por grupo Protheus.
- **Sem cache de permissão.** Uma consulta ao dicionário de grupos por
  requisição; otimizar só se isso aparecer como problema real medido.
- **Sem alteração de `denyTables`/`denyFields`/`allowMutations`.** A nova
  camada de verificação por usuário é adicional a essas, não as substitui.

## Arquitetura

```
custom/backoffice/graphql/
  core/
    access-control.tlpp   -- + isUserAllowed(cGroup, cTable, cOperation)
    auth-context.tlpp      -- NOVO: lê usuário autenticado da sessão REST
                              (UserName()/RetCodUsr(), confirmado ao vivo
                              no planejamento) e seu grupo Protheus
  config/
    graphql-config.json    -- + "groupPermissions": { "<grupo>": {
                              "tables": ["SA1", "SA2"], "mutations": true } }
  entrypoints/
    service.entrypoint.tlpp -- + oAuthContext:new(), passado para
                              GqlAccessControl junto com oConfig
```

`GqlAuthContext` é a única classe nova. Ela isola a única parte
verdadeiramente incerta hoje (qual função AdvPL devolve o usuário
autenticado sob `Security=1` nesta build específica) atrás de uma
interface de duas linhas (`getUserId()`, `getUserGroup()`), do mesmo jeito
que `GqlDictionaryReader` isola os detalhes de SX2/SX3 do resto do motor.

`GqlAccessControl:isTableAllowed`/`isFieldAllowed` continuam do mesmo
jeito (lista de bloqueio estrutural, sem usuário). O método novo,
`isUserAllowed(cGroup, cTable, cOperation)` (`cOperation` = `"read"` ou
`"write"`), consulta `groupPermissions` do config: grupo ausente do mapa →
nega tudo (padrão fechado, não aberto); grupo presente sem a tabela na
lista `tables` → nega; `mutations: false` (ou ausente) → nega qualquer
`create/update/delete`, mesmo que a tabela esteja em `tables` para leitura.

## Ponto de verificação

`GqlExecutor` (leitura) e `GqlMutationExecutor` (escrita) chamam
`isUserAllowed()` no mesmo ponto onde hoje já checam `isTableAllowed()` —
antes de montar a query/escrita, nunca depois. Falha de autorização por
usuário retorna o mesmo formato de erro que a deny-list estrutural já usa
hoje (`GqlErrors`), só com mensagem distinta
(`"User not authorized for table '<X>'"` /
`"User not authorized for mutations on '<X>'"`) — do ponto de vista do
cliente GraphQL, ambas são "Unknown or restricted field/mutation", sem
detalhar se é bloqueio estrutural ou de usuário (não vazar a existência de
uma tabela bloqueada para quem não tem permissão nela).

## Configuração

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "allowMutations": ["SA1"],
  "groupPermissions": {
    "000000": { "tables": ["SA1", "SA2"], "mutations": true },
    "999999": { "tables": ["*"], "mutations": true }
  },
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

`"*"` em `tables` libera todas as tabelas (para o grupo de admin, ex.
`999999`), aceito por reaproveitar `GqlConfig():MatchWildcard()` já
existente — sem lógica nova de wildcard. Grupo não listado em
`groupPermissions` → `isUserAllowed()` sempre `.F.` (fechado por padrão,
diferente das deny-lists estruturais que são abertas por padrão — aqui a
ausência de configuração explícita nunca deveria liberar acesso).

## Risco técnico a verificar empiricamente no planejamento

Não está confirmado nesta build qual função AdvPL devolve o usuário
autenticado dentro de um método `@Get`/`@Post` do TLPP REST quando
`Security=1` está ligado (candidatas: `UserName()`, `RetCodUsr()`,
`__cUserName`, ou um getter do próprio `oRest`). Isso será confirmado
contra o servidor Protheus real (Basic Auth de um usuário de teste real
via `curl -u`) antes de travar o plano de implementação — mesmo método
empírico usado nos gotchas de API dos sub-projetos 1 e 2 — com o resultado
documentado nas Global Constraints do plano. Ligar `Security=1` também
exige confirmar que a suíte de testes atual (`tests/tir/`) continua
executável passando credenciais via `PROTHEUS_REST_BASE`/nova variável de
usuário-senha em `tests/contrib/tir.py`.

## Testes (TIR/Python)

- `test_graphql_auth_missing_credentials.tir` — request sem Basic Auth →
  `401`, nunca chega a `GQLSERVICE`.
- `test_graphql_auth_invalid_credentials.tir` — usuário/senha inválidos →
  `401`.
- `test_graphql_auth_group_denied_table.tir` — usuário autenticado, grupo
  sem a tabela em `groupPermissions` → erro GraphQL "Unknown or
  restricted field", HTTP 200 (erro é do payload GraphQL, não HTTP).
- `test_graphql_auth_group_allowed_table.tir` — usuário autenticado, grupo
  com a tabela liberada → query funciona normalmente.
- `test_graphql_auth_group_mutation_denied.tir` — grupo com a tabela
  liberada para leitura mas `mutations: false` → mutation falha, query na
  mesma tabela funciona.
- `test_graphql_auth_wildcard_group.tir` — grupo com `tables: ["*"]`
  acessa qualquer tabela não bloqueada estruturalmente.

## Dependências para sub-projetos seguintes

- **Field Hooks** (sub-projeto 4) pode querer o usuário autenticado
  disponível para hooks (ex.: campo de auditoria `created_by`) —
  `GqlAuthContext:getUserId()` já fica pronto para isso, sem mudança de
  interface antecipada aqui.
- **Console PO-UI** (sub-projeto 6) provavelmente expõe
  `groupPermissions` como tela de administração — este spec só define o
  formato JSON, a UI fica para aquele sub-projeto.
