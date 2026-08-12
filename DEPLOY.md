# Deploy — GraphQL Protheus

## Pre-requisitos

- TOTVS Protheus 12.1.2510 ou superior
- Appserver configurado com suporte a REST
- TLPP compiler disponivel
- Tabelas SA1, SB1, SC5 presentes no banco de dados

## Passo a Passo

### 1. Copiar arquivos

Copie a pasta `custom/backoffice/graphql/` inteira para o diretorio de fontes do projeto.

### 2. Configurar appserver.ini

Adicione ao arquivo `appserver.ini` do seu ambiente:

```ini
[REST]
/graphql=custom.backoffice.graphql.service.entrypoint
```

Se ja existirem entradas em `[REST]`, adicione a nova linha no final da secao.

### 3. Compilar os fontes

Compile todos os arquivos TLPP na ordem correta (dependencias):

1. `core/types.tlpp`
2. `core/schema.tlpp`
3. `core/parser.tlpp`
4. `core/validator.tlpp`
5. `core/executor.tlpp`
6. `core/executive.tlpp`
7. `schema/customer.types.tlpp`
8. `schema/product.types.tlpp`
9. `schema/invoice.types.tlpp`
10. `resolvers/customer.init.tlpp`
11. `resolvers/product.init.tlpp`
12. `resolvers/invoice.init.tlpp`
13. `resolvers/generic.tlpp`
14. `service.entrypoint.tlpp`

Use o comando de compilacao padrao do Protheus ou TOTVS Developer Studio.

### 4. Reiniciar o appserver

```bash
# Parar o appserver
./stopserver.sh

# Iniciar o appserver
./startserver.sh
```

### 5. Testar o endpoint

```bash
# Teste basico — introspeccao
curl "http://seu-servidor:porta/rest/graphql"

# Teste com query
curl "http://seu-servidor:porta/rest/graphql?query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7B%20codigo%20nome%20%7D%20%7D"

# Teste com filial especifica
curl "http://seu-servidor:porta/rest/graphql?query=%7B%20listCliente(primeiro%3A%205)%20%7B%20codigo%20nome%20cidade%20%7D%20%7D&filial=01"
```

### 6. Executar testes TIR

```bash
pytest tests/tir/test_graphql_sa1.tir -v
pytest tests/tir/test_graphql_sb1.tir -v
```

## Parametros de Sistema (MV)

| Parametro | Padrao | Descricao |
|-----------|--------|-----------|
| `MV_GQLFIL` | (vazio) | Filial padrao para queries GraphQL quando nao informada na request |
| `MV_GQLMAXPAGE` | `100` | Maximo de registros por pagina (hard limit) |
| `MV_GQLLOG` | `0` | 1 = habilitar logs detalhados de execucao |

## Monitoramento

Os logs de execucao GraphQL sao gravados via `FWLogMsg()` no log padrao do appserver. Para habilitar log detalhado:

1. Defina `MV_GQLLOG=1` via `SetMV()` ou `appserver.ini`
2. Verifique o log do appserver em tempo real

## Troubleshooting

| Problema | Solucao |
|----------|---------|
| Erro 404 em `/graphql` | Verificar se entrada `[REST] /graphql=custom.backoffice.graphql.service.entrypoint` existe no appserver.ini |
| Erro de compilacao em `types.tlpp` | Verificar se `tlpp-core.th` e `totvs.ch` estao disponiveis no RPO |
| Query retorna `null` para campo | Verificar se o campo existe na tabela e se o soft-delete (`D_E_L_E_T_`) esta limpo |
| Erro `Unknown field` | Verificar se o tipo foi registrado via `registerModule()` ou se o resolver esta definido |
| Paginacao nao funciona | Verificar se os parametros `primeiro` e `offset` estao sendo passados corretamente |
