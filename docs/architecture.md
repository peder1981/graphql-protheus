# Arquitetura

Pipeline de requisição:

```
GET /graphql --> GQLSERVICE (entrypoints/service.entrypoint.tlpp)
             --> GqlLexer + GqlParser (core/lexer.tlpp, core/parser.tlpp)
             --> GqlValidator (core/validator.tlpp)
             --> GqlExecutor (core/executor.tlpp)
                 --> GqlQueryBuilder (core/query-builder.tlpp)
                 --> GqlDictionaryReader (core/dictionary-reader.tlpp)
             --> Resposta JSON
```

O schema nunca é escrito à mão: `GqlSchemaProvider` (core/schema-provider.tlpp)
monta os tipos GraphQL de forma preguiçosa a partir de SX2 (tabelas) e SX3
(campos), e os campos de relacionamento a partir de SX9. Tabelas/campos são
filtrados pelo `GqlAccessControl` (core/access-control.tlpp) contra as
listas de bloqueio do `config/graphql-config.json` antes de qualquer cache.

Verificações de permissão por usuário estão fora do escopo deste
sub-projeto; o sub-projeto Auth vai adicioná-las, provavelmente como
outro método no `GqlAccessControl`.

## Mutations

`GqlMutationExecutor` (core/mutation-executor.tlpp) é um pipeline de
escrita paralelo ao executor de leitura, compartilhando o mesmo
lexer/parser e o mesmo `GqlDictionaryReader`. Ele escreve pelo caminho
nativo de workarea do Protheus (`GqlWorkareaWriter`,
core/workarea-writer.tlpp) — `RecLock(cTable,.T.)` para inclusão,
`DbSetOrder(1)`+`dbSeek` para posicionar pela chave primária e
`RecLock(cTable,.F.)` para alteração/soft-delete, sempre fechando com
`MsUnlock()` — e não mais via SQL bruto. Isso substitui uma abordagem
anterior (SQL direto via `TCSqlExec()`, já removida) porque
`RecLock(cTable,.T.)` delega a atribuição do `R_E_C_N_O_` (chave física
do registro) à própria camada ISAM/DBAccess, eliminando a corrida
TOCTOU que o `MAX(R_E_C_N_O_)+1` em SQL bruto tinha, e porque o caminho
de workarea é portável identicamente para outros bancos (SQL Server,
Oracle) suportados pelo Protheus, ao contrário de SQL bruto amarrado à
sintaxe do PostgreSQL. A linha afetada é reselecionada através do
`GqlExecutor:resolveTableField()` existente, de modo que a moldagem da
resposta (aliases, seleções aninhadas) nunca é duplicada.

Uma tabela é gravável apenas se estiver em `allowMutations` (configuração)
E ainda passar pela lista de bloqueio do caminho de leitura — as duas
condições se combinam, nenhuma sozinha é suficiente. `GqlInputValidator`
verifica obrigatoriedade/tipo/tamanho contra os metadados do SX3 antes de
qualquer escrita. Exclusão é sempre lógica (`DbDelete()`, marcando
`D_E_L_E_T_ = '*'`), coerente com como toda consulta já filtra leituras.

Um `create` faz antes uma verificação de existência (reaproveitando o
mesmo `locate()` que `update`/`delete` já usam) antes de tentar
`RecLock(cTable,.T.)`. Isso é necessário porque uma violação de chave
única neste backend Postgres surge **assincronamente** — via um flush
de I/O separado do DBAccess, relatado pelo `ErrorBlock` global do
framework num contexto de execução diferente — e não como um erro de
runtime síncrono em `MsUnlock()`; um `begin sequence/recover using`
em torno de `MsUnlock()` foi testado ao vivo e **não** captura esse
caso (`writeCreate()` retornava `.T.` na hora, e o cliente recebia de
volta os dados antigos da linha já existente, parecendo um `create`
bem-sucedido). A verificação prévia fecha o caso comum (cliente
recriando uma chave já ativa) de forma determinística; uma corrida
genuína — dois `create`s para a mesma chave nova chegando no mesmo
instante — ainda pode escapar dessa verificação, um risco residual de
baixa probabilidade, documentado no cabeçalho Protheus.doc de
`writeCreate()` em `workarea-writer.tlpp`.

Campos de entrada desconhecidos ou bloqueados são atualmente ignorados
silenciosamente, não rejeitados com erro explícito: `GqlValidator` nunca é
invocado no caminho de mutation, então um nome de campo que não faz parte
das listas SET/INSERT guiadas pelo dicionário é simplesmente excluído
quando essas listas são montadas — nunca chega ao SQL, então isso não é
um furo de segurança, mas diverge da semântica normal do GraphQL (um
campo desconhecido em um objeto de entrada deveria ser um erro de
validação). Fechar isso fica para a validação de argumentos de mutation
por campo de um sub-projeto futuro.

### Limitação conhecida: corrida em `create` sobre a mesma chave nova

A verificação prévia de existência em `writeCreate()` fecha o caso comum
de duplicidade (chave já ativa), mas uma corrida genuína — dois `create`s
para a **mesma chave nova**, ambos chegando antes de qualquer um
confirmar a escrita — ainda pode escapar, pelo motivo assíncrono
explicado acima. **Garantia de segurança atual**: seguro para uso de
requisição única e baixa concorrência (ex.: os próprios testes deste
sub-projeto). Sob tráfego de produção genuinamente concorrente na mesma
tabela, esse caso extremo permanece um risco residual de baixa
probabilidade, não eliminado.

Veja o cabeçalho Protheus.doc de `writeCreate()` em
`custom/backoffice/graphql/core/workarea-writer.tlpp` para a análise
técnica completa.

## Auth (autenticação e autorização por usuário)

`GqlAuthContext` (core/auth-context.tlpp) isola o único ponto incerto do
sub-projeto Auth — qual função AdvPL devolve o usuário autenticado
(`RetCodUsr()`) e seus grupos (`SYS_USR_GROUPS`, nome físico
`sys_usr_groups` — `RetSqlName()` resolve errado para essa tabela,
confirmado ao vivo). `GqlAccessControl` ganha `isUserAllowed(cTable,
cOperation)`, uma terceira camada de verificação (grupo/usuário) somada à
deny-list estrutural e à allow-list de mutation existentes.

Diferente das outras camadas, esta é **opt-in via config**
(`authEnforced`, padrão `false` em `graphql-config.json`), não
auto-detectada: `RetCodUsr()` devolveu, ao vivo neste ambiente de teste,
um valor não-vazio mesmo sem nenhuma autenticação HTTP (`Security=0`) —
não é um sinal confiável de "existe usuário autenticado nesta
requisição". Com `authEnforced: false` (padrão), `isUserAllowed()` sempre
devolve `.T.` sem tocar o banco, idêntico ao comportamento anterior a
este sub-projeto. Só quando o operador liga `authEnforced: true` (depois
de confirmar, no seu próprio ambiente com `[HTTPREST] Security=1` e
dicionário de empresa/usuário completo, que `RetCodUsr()` reflete
corretamente o usuário da requisição) é que `groupPermissions` passa a
valer, com `OR` entre os grupos do usuário — basta um grupo liberar a
tabela para autorizar.

Neste ambiente de teste específico (dicionário minimalista, sem SM0
completo), `Security=1` faz o próprio pipeline nativo do Protheus
travar com HTTP 500 antes do código deste projeto rodar — confirmado ao
vivo, revertido para `Security=0`. A ativação de ponta a ponta
(`Security=1` + `authEnforced: true`) permanece não validada aqui;
detalhes completos em `docs/superpowers/specs/2026-09-06-graphql-auth-design.md`.