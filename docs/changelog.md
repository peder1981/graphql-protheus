# Changelog — GraphQL Protheus

Todos os lancamentos sao documentados conforme o [Keep a Changelog](https://keepachangelog.com/pt-BR/).

---

## [2.0.0] — 2026-08-11

### Adicionado

- **Self-service buffet** — modulos configuraveis via `appserver.ini`, sem alterar codigo TLPP
- **Auto-discovery SX3** — campos de tabelas descobertos automaticamente do dicionario Protheus
- **Playground interativo** — interface HTML auto-contida em `/graphql/playground`, sem dependencias externas
- **Endpoint `/graphql/modules`** — lista modulos configurados e status do auto-discovery
- **Endpoint `/graphql/schema`** — introspeccao expandida em JSON
- **Configuracao INI completa** — secao `[GraphQL]` no appserver.ini com paginacao, logging, auto-discovery
- **Documentacao completa** — arquitetura, configuracao, API reference, self-service guide, changelog

### Modificado

- **GqlExecutive** — adicao de `loadFromConfig()` e `getModuleMetadata()`
- **README.md** — atualizado com exemplos de configuracao, playground e tabela de modulos
- **DEPLOY.md** — atualizado com passos pos-deploy, verificacao de auto-discovery e access ao playground

### Arquitetura

- Nova classe `GqlConfig` (core/config.tlpp) — parse e acesso ao appserver.ini
- Nova classe `GqlAutoDiscover` (core/autodiscover.tlpp) — discovery via SX3/SX1
- Nova classe `GqlPlayground` (playground.tlpp) — geracao de HTML interativo
- Novo entry point `playground.entrypoint.tlpp` — `/graphql/playground`
- Novo entry point `schema.render.tlpp` — `/graphql/schema`
- Novo entry point `modules.render.tlpp` — `/graphql/modules`

---

## [1.0.0] — 2024-01-01

### Adicionado

- Motor GraphQL nativo em TLPP (parser, validator, executor)
- Suporte a queries GraphQL com argumentos e paginacao
- Endpoints `find*` e `list*` para SA1 (Cliente), SB1 (Produto) e SC5 (NotaFiscal)
- Mapeamento automatico Protheus → camelCase
- Filtros por campo e paginacao ordinal
- Tratamento de erros GraphQL (PARSE_ERROR, VALIDATION_ERROR, EXECUTION_ERROR)
- Tests TIR para SA1 e SB1

---

## Comparativo de Versoes

| Recurso | v1.0.0 | v2.0.0 |
|---------|--------|--------|
| Modulos | Hardcoded em TLPP | Configuraveis via INI |
| Campos | Fixos por arquivo | Manual ou auto-discovery SX3 |
| Playground | Nao existente | HTML inline em `/graphql/playground` |
| Documentacao | Basica | Completa (5 documentos) |
| Extensibilidade | Requer recompilacao | Apenas INI + reinicio |
