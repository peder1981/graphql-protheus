# Deploy — GraphQL Protheus

Guia completo de implantação do motor GraphQL nativo no TOTVS Protheus 12.

## Pré-requisitos

- TOTVS Protheus 12.1.2510 ou superior
- Appserver configurado com suporte a REST
- TLPP compiler disponível no ambiente de compilação
- Tabelas SA1, SB1, SC5 presentes no banco de dados
- Acesso ao arquivo `appserver.ini` do ambiente
- Permissão para reiniciar o appserver

## Passo a Passo

### 1. Copiar arquivos

Copie a pasta `graphql/` inteira para o diretório de fontes do seu projeto Protheus:

```bash
cp -r graphql /caminho/do/projeto/
```

Ou, se estiver usando o TOTVS Developer Studio, importe os arquivos via File → Import.

### 2. Configurar appserver.ini

Adicione ao arquivo `appserver.ini` do seu ambiente a entrada REST:

```ini
[REST]
/graphql=U_GQLSERVICE
```

Se já existirem entradas em `[REST]`, adicione a nova linha no final da seção.

Um exemplo completo está em `graphql/config/appserver-graphql.ini`.

### 3. Compilar os fontes

Compile todos os arquivos TLPP na ordem correta de dependências:

#### Ordem de Compilação

| # | Arquivo | Dependência |
|---|---------|-------------|
| 1 | `graphql/core/gqltypes.tlpp` | Nenhuma |
| 2 | `graphql/core/gqlschema.tlpp` | gqltypes |
| 3 | `graphql/core/gqlparser.tlpp` | Nenhuma |
| 4 | `graphql/core/gqlvalidator.tlpp` | gqltypes, gqlschema |
| 5 | `graphql/core/gqlexecutor.tlpp` | gqltypes, gqlschema, gqlvalidator |
| 6 | `graphql/core/gqlexecutive.tlpp` | gqltypes, gqlschema, gqlparser, gqlvalidator, gqlexecutor |
| 7 | `graphql/schema/gqltypesa1.tlpp` | gqltypes, gqlschema |
| 8 | `graphql/schema/gqltypesb1.tlpp` | gqltypes, gqlschema |
| 9 | `graphql/schema/gqltypesc5.tlpp` | gqltypes, gqlschema |
| 10 | `graphql/resolvers/gqlresolversa1.tlpp` | gqltypes, gqlschema |
| 11 | `graphql/resolvers/gqlresolversb1.tlpp` | gqltypes, gqlschema |
| 12 | `graphql/resolvers/gqlresolversc5.tlpp` | gqltypes, gqlschema |
| 13 | `graphql/resolvers/gqlresolvergeneric.tlpp` | gqltypes, gqlschema |
| 14 | `graphql/entrypoints/U_GQLSERVICE.tlpp` | Todos os acima |

#### Via TOTVS Developer Studio

1. Abra o projeto no TOTVS Developer Studio
2. Selecione todos os arquivos `.tlpp` na pasta `graphql/`
3. Clique com o botão direito → Compile
4. Aguarde a compilação concluir sem erros

#### Via Linha de Comando

```bash
# Exemplo usando tp58run (ajuste o caminho conforme seu ambiente)
tp58run -source graphql/core/gqltypes.tlpp -target RPO
tp58run -source graphql/core/gqlschema.tlpp -target RPO
tp58run -source graphql/core/gqlparser.tlpp -target RPO
tp58run -source graphql/core/gqlvalidator.tlpp -target RPO
tp58run -source graphql/core/gqlexecutor.tlpp -target RPO
tp58run -source graphql/core/gqlexecutive.tlpp -target RPO
tp58run -source graphql/schema/gqltypesa1.tlpp -target RPO
tp58run -source graphql/schema/gqltypesb1.tlpp -target RPO
tp58run -source graphql/schema/gqltypesc5.tlpp -target RPO
tp58run -source graphql/resolvers/gqlresolversa1.tlpp -target RPO
tp58run -source graphql/resolvers/gqlresolversb1.tlpp -target RPO
tp58run -source graphql/resolvers/gqlresolversc5.tlpp -target RPO
tp58run -source graphql/resolvers/gqlresolvergeneric.tlpp -target RPO
tp58run -source graphql/entrypoints/U_GQLSERVICE.tlpp -target RPO
```

### 4. Reiniciar o appserver

```bash
# Parar o appserver
./stopserver.sh

# Iniciar o appserver
./startserver.sh
```

### 5. Testar o endpoint

#### Introspecção (schema completo)

```bash
curl "http://seu-servidor:porta/rest/graphql"
```

Resposta esperada: JSON com `data.__schema` contendo os tipos registrados.

#### Consulta findCliente

```bash
curl "http://seu-servidor:porta/rest/graphql?query={%20findCliente(codigo:%20%22000001%22)%20{%20codigo%20nome%20cidade%20}%20}"
```

Resposta esperada:

```json
{
  "data": {
    "findCliente": {
      "codigo": "000001",
      "nome": "EMPRESA TESTE LTDA",
      "cidade": "SAO PAULO"
    }
  }
}
```

#### Lista com paginação

```bash
curl "http://seu-servidor:porta/rest/graphql?query={%20listClientes(primeiro:%205,%20offset:%200,%20cidade:%20%22SAO%20PAULO%22)%20{%20codigo%20nome%20telefone%20}%20}"
```

#### Com filial específica

```bash
curl "http://seu-servidor:porta/rest/graphql?query={%20findCliente(codigo:%20%22000001%22)%20{%20codigo%20nome%20}%20}&filial=01"
```

### 6. Executar testes TIR

```bash
# Executar todos os testes TIR
pytest tests/tir/ -v

# Executar teste específico
pytest tests/tir/test_graphql_sa1.tir -v
pytest tests/tir/test_graphql_sb1.tir -v
pytest tests/tir/test_graphql_sc5.tir -v
```

## Parametros de Sistema (MV)

| Parametro | Padrão | Descrição |
|-----------|--------|-----------|
| `MV_GQLFIL` | (vazio) | Filial padrão para queries GraphQL quando não informada na request. Quando vazio, usa `xFilial()` da tabela correspondente. |

## Monitoramento

Os logs de execução GraphQL são gravados via `FWLogMsg()` no log padrão do appserver.

Para habilitar log detalhado, defina no código ou via SetMV:

```tlpp
// No entry point ou em um inicializador
SetMV("MV_GQLLOG", "1")
```

Verifique o log do appserver em tempo real:

```bash
tail -f /caminho/do/appserver/log/appserver.log
```

Mensagens de log incluem:
- Registro de tipos no schema: `GqlSchema: registered type 'Cliente'`
- Campos registrados: `GqlExecutive: registered field 'codigo' on type 'Cliente'`
- Erros de compilação e execução
- Queries SQL executadas (via `GqlGenericResolver`)

## Troubleshooting

| Problema | Causa Provável | Solução |
|----------|---------------|---------|
| Erro 404 em `/graphql` | Entrada `[REST]` não configurada no appserver.ini | Verificar se `/graphql=U_GQLSERVICE` existe na seção `[REST]` do appserver.ini |
| Erro de compilação em `gqltypes.tlpp` | `tlpp-core.th` ou `totvs.ch` não encontrados | Verificar se os includes estão disponíveis no RPO do projeto |
| Query retorna `null` para campo | Campo não existe na tabela ou soft-delete ativo | Verificar se o campo existe no dicionário SX3 e se `A1_DELET = ' '` (SA1) ou `B1_DELET = ' '` (SB1) |
| Erro `Unknown field` | Tipo não registrado ou resolver não definido | Verificar se o módulo foi registrado em `U_GQLSERVICE` ou via `registerModule()` |
| Paginação não funciona | Parâmetros `primeiro`/`offset` ausentes ou com valor inválido | Garantir que os parâmetros são passados como números inteiros |
| Erro de sintaxe GraphQL | Query mal formada ou caracteres especiais não escapados | Usar URL encoding correto para caracteres especiais (aspas, espaços) |
| Resultado vazio em `findCliente` | Código do cliente não existe ou filial incorreta | Verificar se o código existe na filial especificada |
| Erro `Cannot read property 'getName'` | Schema não inicializado antes da execução | Garantir que os módulos são registrados antes de executar queries |
| Logs não aparecem | `FWLogMsg` desabilitado ou nível de log insuficiente | Verificar configuração de log do appserver |
| Erro de encoding em caracteres acentuados | Arquivos salvos em UTF-8 em vez de CP-1252 | Converter arquivos para CP-1252 usando a ferramenta de conversão do Protheus |

## Checklist de Implantação

- [ ] Arquivos `.tlpp` copiados para o projeto
- [ ] Entrada `[REST] /graphql=U_GQLSERVICE` adicionada ao appserver.ini
- [ ] Todos os 14 arquivos compilados sem erros
- [ ] Appserver reiniciado
- [ ] Introspecção retorna JSON com tipos registrados
- [ ] `findCliente` retorna dados corretos
- [ ] `listClientes` retorna lista paginada
- [ ] `findProduto` retorna dados corretos
- [ ] `listProdutos` retorna lista paginada
- [ ] `findNotaFiscal` retorna dados corretos
- [ ] `listNotasFiscais` retorna lista paginada
- [ ] Parâmetro `filial` funciona corretamente
- [ ] Logs de execução aparecem no appserver log
- [ ] Testes TIR passam (se disponíveis)

## Rollback

Em caso de problemas, para remover o motor GraphQL:

1. Remova a entrada `[REST] /graphql=U_GQLSERVICE` do appserver.ini
2. Remova os arquivos `.tlpp` do projeto
3. Reinicie o appserver

O motor GraphQL será desativado sem afetar as tabelas ou funcionalidades existentes do Protheus.
