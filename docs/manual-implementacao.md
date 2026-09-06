# Manual de Implementação

Guia completo para quem vai instalar, configurar e operar este motor
GraphQL em um ambiente Protheus. Público-alvo: administradores de
ambiente e desenvolvedores responsáveis pelo deploy.

## Visão geral da estrutura

```
custom/backoffice/graphql/
  config/
    graphql-config.json        -- lista de bloqueio, liberação de mutations, paginação
  core/
    lexer.tlpp                 -- tokeniza o texto GraphQL recebido
    parser.tlpp                 -- monta a árvore de sintaxe (AST) a partir dos tokens
    validator.tlpp               -- valida a AST contra o schema (leitura)
    dictionary-reader.tlpp        -- leitura crua de SX2/SX3/SX9/SIX
    access-control.tlpp            -- aplica a lista de bloqueio de config
    schema-provider.tlpp            -- gera e cacheia o schema GraphQL dinamicamente
    query-builder.tlpp               -- monta o SQL de leitura (SELECT paginado)
    executor.tlpp                     -- orquestra leitura: valida, executa, resolve relações
    introspection.tlpp                 -- responde __schema/__type
    errors.tlpp                         -- monta o envelope {"errors": [...]}
    mutation-schema.tlpp                 -- expõe create/update/deleteTABLE só para tabelas liberadas
    input-validator.tlpp                  -- valida input de mutation contra SX3
    workarea-writer.tlpp                   -- escreve via RecLock/FieldPut/MsUnlock (workarea nativa)
    mutation-executor.tlpp                  -- orquestra escrita: valida, escreve, reseleciona
  entrypoints/
    service.entrypoint.tlpp                  -- ponto de entrada REST único (@Get /graphql)
```

Nenhum tipo GraphQL é escrito à mão. Todo o schema é gerado em tempo de
execução a partir do dicionário de dados do Protheus (SX2, SX3, SX9,
SIX), com cache em memória por processo do AppServer.

## Pré-requisitos de ambiente

- AppServer Protheus com o framework REST habilitado
  (`[HTTPREST]` no `appserver.ini`, escutando na porta configurada —
  `9995` nos exemplos deste manual).
- Backend de banco de dados: o motor foi desenvolvido e testado contra
  **PostgreSQL**. A escrita usa o caminho nativo de workarea
  (`RecLock`/`FieldPut`/`MsUnlock`), projetado para ser portável
  identicamente a outros bancos suportados pelo Protheus (SQL Server,
  Oracle, DB2) — mas só validado ao vivo contra PostgreSQL até aqui.
- Ferramental de compilação de fontes `.tlpp` para o seu ambiente
  (`appsrvlinux -compile` ou equivalente).

## Passo a passo de deploy

### 1. Compilar os fontes

Compile, na ordem de dependência abaixo, todos os arquivos de
`custom/backoffice/graphql/core/` seguidos de
`custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp`:

```
config.tlpp
access-control.tlpp
dictionary-reader.tlpp
schema-provider.tlpp
lexer.tlpp
parser.tlpp
validator.tlpp
query-builder.tlpp
executor.tlpp
errors.tlpp
introspection.tlpp
mutation-schema.tlpp
input-validator.tlpp
workarea-writer.tlpp
mutation-executor.tlpp
entrypoints/service.entrypoint.tlpp
```

Compilar o conjunto inteiro junto (não só o arquivo alterado) evita erros
de "classe inválida" quando o ambiente de compilação não tem as classes
de uma sessão anterior em cache.

### 2. Implantar o RPO

Copie o RPO compilado para o AppServer de destino e reinicie o processo,
seguindo o processo padrão do seu ambiente.

### 3. Implantar o arquivo de configuração (passo manual obrigatório)

**Este é o passo mais fácil de esquecer, e o mais silencioso quando
esquecido.**

`custom/backoffice/graphql/config/graphql-config.json` **não** é um fonte
`.tlpp` — ele nunca entra no RPO compilado. Ele precisa ser copiado
manualmente para o sistema de arquivos do servidor, no caminho:

```
<RootPath>/custom/backoffice/graphql/config/graphql-config.json
```

Onde `<RootPath>` é o valor de `[P12] RootPath=` no `appserver.ini` do
ambiente de destino — **não** o `SourcePath`, e não o diretório de
trabalho do processo do AppServer. Isso foi confirmado por teste direto
contra um servidor real: `MemoRead()` (a função que a classe `GqlConfig`
usa para ler o JSON) resolve caminhos relativos contra o `RootPath`,
ignorando as outras três localizações candidatas testadas.

**Consequência de esquecer este passo**: `GqlConfig:new()` não encontra o
arquivo, cai silenciosamente nos valores padrão embutidos (lista de
bloqueio vazia, nenhuma tabela liberada para mutation), e **todas as
tabelas do dicionário ficam visíveis e legíveis via GraphQL** — incluindo
tabelas sensíveis como `SRH*` (Recursos Humanos), a menos que o
`graphql-config.json` real esteja de fato no lugar certo. Sempre confirme
após o deploy:

```bash
curl "http://localhost:9995/rest/graphql" | grep -o '"SRA"'
```

Não deve haver saída (assumindo `SRA` na sua lista de bloqueio) — se
aparecer, o arquivo de configuração não foi encontrado pelo servidor.

### 4. Confirmar que o serviço está no ar

```bash
curl "http://localhost:9995/rest/graphql"
```

Deve retornar a lista de tipos disponíveis (`__schema.types`).

## Arquivo de configuração — referência completa

`custom/backoffice/graphql/config/graphql-config.json`:

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "allowMutations": ["SA1"],
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

| Chave | Tipo | Significado |
|---|---|---|
| `denyTables` | array de strings com curinga | Aliases de tabela nunca expostos, ex. `"SRH*"` |
| `denyFields` | array de strings com curinga | Nomes de campo nunca expostos, ex. `"*SENHA*"` |
| `allowMutations` | array de aliases exatos (sem curinga) | Tabelas que aceitam `createTABLE`/`updateTABLE`/`deleteTABLE`; vazio por padrão (tudo somente leitura) |
| `pagination.defaultPageSize` | número | `limit` usado quando a consulta não informa um |
| `pagination.maxPageSize` | número | Teto rígido de `limit`, mesmo que a consulta peça mais |
| `schemaCacheTtlSeconds` | número | Tempo que o tipo gerado de uma tabela fica em cache antes de ser reconstruído automaticamente |

Curingas (`*`) funcionam como "qualquer sequência de caracteres" e
aplicam-se apenas a `denyTables`/`denyFields`. `allowMutations` exige o
alias exato — não aceita curinga, por design: liberar escrita é uma
decisão por tabela, não um padrão amplo.

Tabelas/campos bloqueados nunca aparecem em introspecção nem em
resultado de consulta, independentemente da forma da query. Uma tabela
só é gravável se estiver **ao mesmo tempo** em `allowMutations` **e**
ausente de `denyTables` — as duas condições precisam valer juntas.

## Limitações conhecidas (leia antes de liberar tabelas em produção)

### Corrida em `create` sobre a mesma chave nova

Mutations de `create` escrevem via `RecLock(cTable,.T.)` (caminho nativo
de workarea) — isso delega a atribuição do `R_E_C_N_O_` (chave física de
registro) à própria camada ISAM/DBAccess, eliminando a corrida que uma
abordagem anterior via SQL bruto (`MAX(R_E_C_N_O_)+1`, já removida)
tinha. Antes de tentar o `RecLock`, o motor também faz uma verificação
prévia de existência da chave de negócio (reaproveitando o `locate()`
que `update`/`delete` já usam), rejeitando de forma limpa o caso comum
de um `create` repetido para uma chave já ativa.

**Risco residual, não eliminado**: uma violação de chave única neste
backend Postgres surge de forma assíncrona (um flush de I/O separado do
DBAccess, fora do fluxo de execução da requisição original) — por isso
uma corrida **genuína**, com dois `create`s para a **mesma chave nova**
chegando praticamente ao mesmo instante, ainda pode escapar da
verificação prévia. **Garantia de segurança atual**: seguro para uso de
requisição única ou baixa concorrência (ex.: os próprios testes deste
sub-projeto). Sob tráfego de produção genuinamente concorrente na mesma
tabela, esse caso extremo permanece um risco de baixa probabilidade.
Veja o cabeçalho Protheus.doc de `writeCreate()` em
`workarea-writer.tlpp` para a análise técnica completa.

### Casamento de linha em update/delete depende do índice SIX

`update`/`delete` identificam a linha certa usando a chave de ordem 1 do
índice `SIX` da tabela. Em ambientes onde `RetSqlName("SIX")` não
resolve (comum em instalações de desenvolvimento/teste), o motor tenta
um segundo caminho, derivando o nome físico da tabela `SIX` a partir do
sufixo de empresa já usado por `RetSqlName("SX3")` — e só recorre ao
primeiro campo escalar da tabela como último recurso. Se nenhuma das
duas formas encontrar a chave real de order 1, o casamento cai para um
único campo, o que pode fazer `update`/`delete` afetar a linha errada em
tabelas com mais de uma linha ativa por filial.

**Antes de liberar uma nova tabela em `allowMutations`**, confirme que
sua chave de ordem 1 é corretamente identificada: crie dois registros de
teste na mesma filial, diferindo apenas no campo que deveria ser único
(ex. o código), faça um `update` em apenas um deles e confirme que o
outro permanece inalterado:

```graphql
mutation { createTABELA(input: {COD: "TESTE1", ...}) { COD } }
mutation { createTABELA(input: {COD: "TESTE2", ...}) { COD } }
mutation { updateTABELA(input: {COD: "TESTE1", ..., NOME: "Alterado"}) { NOME } }
```

Se o registro `TESTE2` também aparecer alterado (ou se `updateTABELA`
com uma chave inexistente retornar sucesso em vez de
`"Row not found for update"`), a tabela não deve ser liberada para
mutation até o índice `SIX` correspondente ser corrigido no ambiente.

### Sem validações automáticas do Protheus no caminho de escrita

Mutations não passam pelo `FWFormModel`/MVC — nenhum trigger `SX7`, regra
de negócio de rotina, ou fórmula `X3_VALID` é executada. A única
validação aplicada é a que o motor faz explicitamente: campo obrigatório
(`X3_OBRIGAT`), tipo e tamanho máximo (`X3_TAMANHO`), a partir do SX3.

### Campos desconhecidos no `input` são ignorados silenciosamente

Se o cliente enviar no `input` de uma mutation um campo que não existe
na tabela (ou que está bloqueado por `denyFields`), o motor simplesmente
o ignora — não gera erro. Isso não é uma falha de segurança (o campo
nunca chega a ser escrito, já que as listas de campos usadas na escrita
vêm sempre do dicionário, nunca diretamente do `input` do cliente), mas
diverge da semântica usual do GraphQL, onde um campo desconhecido em um
objeto de entrada normalmente gera erro de validação. Fica para um
sub-projeto futuro (Auth) fechar essa lacuna.

## Sem geração automática de chave

O cliente sempre precisa enviar o(s) campo(s) de chave no `input`,
inclusive em `create` — o motor não gera código automaticamente via SX5
(`GetSxeNum()`). Quem precisar de numeração automática deve gerar a
chave antes de chamar a mutation.

## Testes

Testes end-to-end em Python (convenção TIR) ficam em `tests/tir/`.
Execute com `pytest tests/tir/ -v` contra um AppServer Protheus real com
este RPO implantado — `tests/conftest.py` (coletor pytest para arquivos
`.tir`) e `tests/contrib/tir.py` (um `Webapp` REST leve, via `urllib`,
com a mesma superfície do `tir.Webapp` original) tornam a suíte
executável localmente sem depender do framework TIR completo
(Selenium/browser). A URL base do endpoint é configurável via a
variável de ambiente `PROTHEUS_REST_BASE` (padrão:
`http://localhost:9996/rest`). Não há suíte de testes unitários
AdvPL/TLPP neste projeto — toda verificação é via HTTP, ao vivo, contra
um servidor real.

## Roteiro de sub-projetos

Este motor faz parte de um roteiro maior em 6 sub-projetos:

1. **Core Engine** (leitura) — concluído
2. **Mutations** (escrita) — concluído, este manual
3. **Auth** — implementado (código + config `authEnforced`/`groupPermissions`);
   ativação real (`[HTTPREST] Security=1`) depende de uma instância com
   dicionário de empresa/usuário completo — ver
   `docs/superpowers/specs/2026-09-06-graphql-auth-design.md`
4. **Field Hooks** — implementado (código + config `fieldHooks`);
   validação end-to-end de um hook bem-sucedido depende de resolver uma
   limitação de ambiente com despacho dinâmico de função nova — ver
   `docs/superpowers/specs/2026-09-06-graphql-field-hooks-design.md`
5. **SDK Generator** — implementado e validado ao vivo (`?sdk=<TABLE>`
   gera classe TLPP tipada) — ver
   `docs/superpowers/specs/2026-09-06-graphql-sdk-generator-design.md`
6. **Console PO-UI** — interface administrativa

Cada sub-projeto tem sua própria especificação em
`docs/superpowers/specs/`.
