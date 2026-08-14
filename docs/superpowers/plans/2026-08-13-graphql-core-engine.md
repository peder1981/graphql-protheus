# GraphQL Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy static-schema GraphQL server with a new TLPP engine that exposes the Protheus data dictionary (SX2/SX3/SX9) as a dynamic, lazily-cached GraphQL schema, with deny-list + permission-hook access control, filtered/paginated queries, and SX9-driven nested relationships.

**Architecture:** A layered pipeline — `dictionary-reader` (raw SX2/SX3/SX9 access) → `access-control` (deny-list + permission stub) → `schema-provider` (lazy cached GraphQL types) → `lexer`/`parser` (GraphQL text → AST) → `validator` (AST vs schema) → `query-builder` (AST → bound SQL) → `executor` (orchestrates everything, resolves nested relations, builds the JSON response). A single REST entry point (`GQLSERVICE`) fronts it all.

**Tech Stack:** TLPP (namespace `custom.backoffice.graphql`), Protheus AppServer REST (`@Get` annotation + implicit `oRest` — `tlpp-rest.th`), JSON (`JsonObject():New()`/`:FromJson()`/`:toJson()` + `json[key]` bracket access), `FWExecStatement`/`ChangeQuery` for SQL, TIR/Python (pytest + `contrib.tir.Webapp`) for e2e tests, `~/.shared/protheus/compile/scripts/{compile.sh,compile-all.sh,deploy-rpo.sh}` (compile-protheus infra) for build/deploy.

**Spec:** `docs/superpowers/specs/2026-08-13-graphql-core-engine-design.md`

## Global Constraints

- Every generated SQL query MUST include the current branch filter (`<real filial field> = <current branch>`, see the Global Constraints note on the branch field/value below) and `D_E_L_E_T_ = ' '` — never optional, never overridable by the caller (spec: Execução de queries). The spec's `%nolock%` requirement is dropped in this plan: verified against the live server that this deployment's database backend is PostgreSQL (`appserver.ini`'s `[DBAccess] Database=POSTGRES`), `%nolock%` is a SQL Server-only table hint with no PostgreSQL equivalent (`ERROR: syntax error at or near "%"`, confirmed at runtime — `ChangeQuery()` does not translate or strip it either, it doubles the `%` instead and still fails), and PostgreSQL's MVCC gives every read a consistent snapshot without blocking on concurrent writers, which is what `%nolock%` exists to work around on SQL Server. Filial and soft-delete filtering (the actual data-correctness requirements) are unaffected and remain mandatory.
- All SQL values from the client (filter values, `type`/table names used to look up dictionary rows) MUST go through bind parameters or `RetSqlName`/dictionary lookups — never string-concatenated into SQL (CLAUDE.md: SQL injection prevention; spec: Execução de queries).
- Denied tables/fields (deny-list match) must never appear in introspection output, regardless of query shape (spec: Restrição de acesso, evaluated before the permission hook).
- The permission hook (`AccessControl():AllowField`) must always return `.T.` in this sub-project (no real auth exists yet) and must be called from exactly one place so sub-project 3 (Auth) can wire it up without touching call sites (spec: Restrição de acesso).
- No relationship nesting depth limit in this phase — do not add one speculatively (spec: Não-objetivos).
- **Test strategy**: this repo has no AdvPL/TLPP unit-test runner (confirmed: no ProBat setup, no `.prw` fixtures) — the existing project's only test layer is TIR (e2e over HTTP), and the design brainstorming explicitly kept that. Per-task verification therefore uses `compile.sh` (must compile with zero errors) as the fast local signal for logic-only files, and TIR (`pytest`) as the runtime signal for tasks that produce new HTTP-observable behavior. This is not a shortcut — it matches the project's existing, deliberate testing convention.
- **Symbol validation**: per this project's CLAUDE.md, every AdvPL/TLPP framework symbol (function/class/method) must be validated against the official docs MCP (`language-system-docs-search`, `product-docs-search`, `execute-sql`) before being treated as final. Those MCP tools were not reachable during planning — every task below is flagged with the exact symbols to validate first; do not skip that check just because the code below looks plausible.
- Encoding of all new `.tlpp`/`.json` files: UTF-8 for `.json` (JSON spec requires it), CP-1252 for all `.tlpp` sources (project convention).
- **TLPP class syntax — verified empirically against the real compiler** (`~/.shared/protheus/compile/scripts/compile.sh`, image `protheus-compile-tlpp:latest`) during Task 2, after the first draft of this plan used a single-block class style that does not compile (C2021 "Invalid definition inside CLASS...ENDCLASS definition"):
  - Every method — instance or `static` — is **declared** inside `class ... endclass` with its full signature (params AND return type), e.g. `public method foo(x as numeric) as logical` or `static method Bar(x as numeric) as numeric`. It is **implemented** separately, after `endclass` and before `endnamespace`, repeating the full signature but dropping every access/static modifier and appending `class ClassName`: `method foo(x as numeric) as logical class MyClass ... endmethod` (a `static` kept on the implementation line is itself a syntax error, C2003).
  - A method with no meaningful return value still needs a declared return type (`as object` works well) and an explicit `return self` on every exit path — a bare `return`/no return against a declared type is a compiler type-mismatch error, not a warning.
  - `endmethod` after an out-of-class implementation compiles fine (verified) — moving a body out of `class...endclass` is the only structural change needed; internal indentation is irrelevant to the compiler.
  - Every class block in this plan already reflects this — do not "simplify" back to single-block style.
- **No cross-file `#include` of this project's own `.tlpp` class files** — verified empirically: including a file that itself declares `namespace...endnamespace` produces C9906 "Only one NAMESPACE is permitted" once both blocks land in the same compiled unit. `compile.sh`/the shared RPO (`build/custom.rpo`) link classes across files automatically once each file has been compiled once — a later file can call `GqlConfig():new()` etc. without including `config.tlpp`, as long as `config.tlpp` was compiled first (which the task order in this plan already guarantees). Only `#include "tlpp-core.th"` and `#include "totvs.ch"` belong at the top of these files.
- **`Local`/`Private` declarations must all sit at the top of a function/method, before any executable statement** — a `local` after an `if`, loop, or assignment is a compile error (C2051 "LOCAL declaration follows executable statement"), not just a style preference. When a later task step adds a variable to an existing method (e.g. Task 4 extending `getType()`), add its `local` to the method's existing top-of-method block, never inline at the point of use.
- **`IIF()` is forbidden** (this project's CLAUDE.md, SonarQube CA4000) — use explicit `If/Else/EndIf` and an intermediate local instead, even for a one-line conditional value.
- These four rules were not caught by planning-time reasoning alone — they surfaced only once real compilation became available mid-Task-2. Every task below has already been corrected to follow them; an implementer who still hits a compile error from one of these categories should treat it as a plan bug to report, not something to route around silently.
- **JSON API — verified empirically against the real running server** (containers `protheus`/`dbaccess`/`postgresql`/`license-server`, already running in this environment) during Task 3. The first draft of this plan used `JsonParse()`, `JsonSet()`, `JsonStringify()`, and `JsonGet()` — none of these functions exist in this Protheus build (confirmed at runtime: `InterFunctionCall: cannot find function JSONSTRINGIFY in AppMap`, same for `JsonParse`). The real API, confirmed working end-to-end against the live server:
  - Create: `local oX as json` then `oX := JsonObject():New()` (or combined: `local oX := JsonObject():New() as json`). Do **not** initialize a fresh JSON object with a bare `{}` literal typed `as json` — an empty `{}` behaves as a plain array at runtime (`type mismatch in array subscriptor - expected N->C` when you then try `oX["key"] := ...`), not a JSON object. `JsonObject():New()` is always safe.
  - Parse a string: `oX := JsonObject():New()` then `uErr := oX:FromJson(cSourceString)` — `uErr` is `Nil` (ValType `"U"`) on success, an error-message character string on failure. There is no standalone `JsonParse()` function.
  - Read/write a property: `oX["key"]` and `oX["key"] := value` — plain bracket access, including chained/nested reads and writes (`oX["a"]["b"]`, `oArr[1]["x"]`) — this **is** supported and requires no change from what earlier drafts of this plan already did; only the construction/parsing/serialization calls needed to change.
  - Serialize to a string: `oX:toJson()` — there is no standalone `JsonStringify()` function.
  - Arrays of JSON objects: build with plain AdvPL arrays (`local aArr := {} as array`, `AAdd(aArr, oItem)`), then assign the whole array to a JSON property (`oParent["items"] := aArr`) — this works and round-trips through `:toJson()` correctly.
  - Every class in this plan already reflects this — do not reintroduce `JsonParse`/`JsonSet`/`JsonStringify`/`JsonGet`.
- **REST entry points use the `@Get` annotation, not a bare `User Function` read via `GetParam`** — verified empirically: a plain `User Function GQLSERVICE()` compiles fine but returns 404 at `/rest/graphql` (Protheus's REST framework, listening on port 9995 per `appserver.ini`'s `[HTTPREST]`, only routes annotated or `WSRESTFUL`-registered functions). The working pattern, confirmed against the live server (`docker exec protheus ...`, `curl http://localhost:9995/rest/graphql`) and matching this environment's own other REST sources (`BLUREST01.tlpp` in the shared compile image):
  - `#include "tlpp-rest.th"` (in addition to `tlpp-core.th`/`totvs.ch`).
  - `@Get("/path")` directly above `User Function Name() as logical`.
  - Inside the function, an `oRest` variable is available **without being declared** — the `@Get` framework injects it into scope. Declaring `local oRest` shadows it and breaks the endpoint.
  - Read query-string params: `oRest:getQueryRequest()` returns a `json`; read individual params via bracket access or `:GetJsonText("name")`.
  - **`:GetJsonText("name")` returns the literal 4-character string `"null"` — not an empty string, not `Nil` — when `name` isn't present in the request.** Confirmed against the live server: `!empty(cQuery)` was `.T.` for a request with no `query` param at all, because `cQuery` held `"null"`. Every `:GetJsonText()` read of an optional query-string param must explicitly check `if cValue == "null" ... cValue := "" ... endif` before using `empty()`/`!empty()` on it. This gotcha is specific to `:GetJsonText()` — plain bracket access (`oX["key"]`) on a missing key correctly returns real `Nil` (`ValType` `"U"`) and needs no such guard; every `!= nil`/`== nil` check on parsed/constructed JSON elsewhere in this plan already relies on that and is unaffected.
  - Send the response: `oRest:setStatusResponse(200, cJsonString)` (build `cJsonString` via `oX:toJson()`) — replaces `FWSetHeader`/`FWPrintHTML`, which are not part of this REST framework's response path.
  - The entry point in this plan already reflects both of these.
- **SQL execution uses `TCQuery ... New Alias &cAlias` (`topconn.ch`), not `FWExecStatement`** — verified empirically: `FWExecStatement` does not exist in this Protheus build (`InterFunctionCall: cannot find function FWEXECSTATEMENT in AppMap`, confirmed at runtime). The real, working pattern (matching this environment's own other REST/SQL sources):
  - `#include "topconn.ch"` (in addition to `tlpp-core.th`/`totvs.ch`) in any file that runs a query.
  - `local cAlq := GetNextAlias() as character` then `TCQuery cSql New Alias &cAlq` — the `&` (macro-expand) operator is required to use a *variable's* value as the alias; `Alias cAlq` (bare) or `Alias (cAlq)` both fail to compile/bind correctly. A literal alias (`Alias "SOMEALIAS"`) also works but a dynamic one is required here since query execution is recursive (nested relationship resolution) and needs a fresh alias per call.
  - Workarea navigation after that (`(cAlq)->(dbGoTop())`, `(cAlq)->(dbSkip())`, `(cAlq)->(Eof())`, `(cAlq)->(dbCloseArea())`, `(cAlq)->(FieldGet(FieldPos(...)))`) is unchanged from earlier drafts of this plan and works as already written.
  - **`TCQuery` has no bind-parameter mechanism** — it takes a single, fully-formed SQL string. Every value that reaches SQL text built by `GqlQueryBuilder` (the filial value, filter values, the parent-key value for nested relationship queries) MUST go through `GqlQueryBuilder():EscapeValue(cValue)` (single-quote doubling — `StrTran(cValue, "'", "''")`) and be wrapped in `'...'` — this replaces the bind-array design in earlier drafts of this plan. `ChangeQuery()` is dropped too (unneeded — `TCQuery` ran the plan's raw SQL correctly against the live server without it).
  - Every file in this plan that executes SQL already reflects this.
- **`RetSqlName("SX9")` and `RetSqlName("SIX")` returned empty strings against the live server this plan was verified against** — these dictionary tables aren't registered as physical tables in every Protheus deployment (unlike `SX2`/`SX3`, confirmed present and working). An empty `RetSqlName()` result concatenated straight into `" FROM " + cTable + " WHERE ..."` produces `FROM  WHERE ...` — a SQL syntax error (Postgres `42601`), not a graceful "no data" result. `getRelations()` and `getOrderKey()` in this plan both check `empty(RetSqlName(...))` first and degrade gracefully (empty relations list; scalar-field fallback for ordering) instead of running the malformed query — do not remove these guards as "unnecessary" defensive code. If a target deployment does have `SX9`/`SIX` registered, these same guards are harmless (the `if empty(...)` branch simply never triggers) — no environment-specific code path to maintain.
- **A table's branch field is never `<table alias> + "_FILIAL"`** — verified against the live server: `SA1`'s real branch field is `A1_FILIAL` (`ERROR: column "sa1_filial" does not exist` when the naive guess was tried). The field prefix (here `A1`) is a per-table SX3 convention, not derivable from the table alias by string manipulation. `GqlDictionaryReader:getFilialField(cTable)` looks it up from SX3 (suffix match on `_FILIAL`) and every place that builds the mandatory filial filter uses its result — never reconstruct this field name from `cTable` directly.
- **`xFilial()`/`FWxFilial()` return blank inside an `@Get`-annotated REST function in this environment** — verified against the live server: both returned `"  "` (empty/blank) even though the correct branch was demonstrably active (72 real `SA1` rows all have `A1_FILIAL = '01'`). The Public variable `cFilAnt` is reliably populated in this same context (confirmed `"01"`, matching `appserver.ini`'s `[HTTPURI] PrepareIn=99,01`) and is what this plan uses for the current-branch value in the mandatory filial filter — `GqlQueryBuilder:build()` reads `cFilAnt` directly, never `xFilial()`/`FWxFilial()`. `cEmpAnt` (current company) is populated too but this plan doesn't currently need it. This is scoped to the branch *value*; `GqlDictionaryReader:getFilialField()` (the branch *field name* lookup, previous bullet) is unrelated and still needed.
- **`custom/backoffice/graphql/config/graphql-config.json` must be deployed to the AppServer's source path separately from the compiled RPO** — verified against the live server: `compile.sh`/`deploy-rpo.sh` only ever handle `.tlpp` sources compiled into `build/custom.rpo`; a loose `.json` resource file is never part of that RPO and `deploy-rpo.sh` does not copy it anywhere. Without it physically present on the server filesystem, `GqlConfig:new()`'s `MemoRead()` finds nothing, silently falls back to its empty built-in deny-list, and **every table becomes visible** — confirmed live: `SRA`/`SR5` (both explicitly deny-listed) appeared in `__schema.types` until the JSON file was copied to the same directory as the compiled sources (`/protheus12/apo/custom/backoffice/graphql/config/graphql-config.json` in this environment — i.e. the AppServer's `SourcePath` from `appserver.ini`'s `[P12] SourcePath=`), after which they correctly disappeared. This is a deployment step, not a code defect — `GqlConfig`'s graceful fallback-to-defaults behavior when the file is missing is intentional and stays as designed (spec: config loading). Task 10's README/deployment docs must call this out explicitly as a required manual step distinct from running `deploy-rpo.sh`, or the deny-list silently does nothing in production.
- **AdvPL string literals do not process C-style backslash escapes** — a real authoring bug in an earlier draft of this plan's lexer, caught only by testing actual GraphQL string-literal parsing against the live server. Writing `cCh == "\""` to compare a character against a double-quote does not do what it looks like it does (the token comparison silently never matched, so every `"` in GraphQL query text fell through to a generic `PUNCT` token instead of starting a string literal, breaking every string argument/filter value). The fix, already applied everywhere in this plan: represent a `"` as a single-quoted literal (`'"'`) and a lone `\` the same way (`'\'`) — never rely on backslash-escaping inside a same-delimiter string. Any future edit to `GqlLexer:scanString()`/`scan()` must preserve this.
- **`oArgs["filter"]` (and every other GraphQL argument value) is the AST *ValueNode wrapper* `{kind, value}`, not the raw value** — a real bug in an earlier draft of `GqlValidator:validateArguments()` and `GqlQueryBuilder:applyFilters()`, both of which did `local aFilters := oArgs["filter"] as array` and got a JSON object, not an array (`valtype()` never `"A"`, or a `nil`-vs-wrapper mismatch depending on the check). The correct access is `oArgs["filter"]["value"]` for the actual array — exactly the same unwrapping `resolveLimit()`/`resolveOffset()` already did correctly for `oArgs["limit"]["value"]`/`oArgs["offset"]["value"]`. Both fixed in this plan; confirmed live with a real filtered query (`filter: [{field: "A1_COD", op: "eq", value: "000001"}]`) returning exactly the one matching row.

---

### Task 1: Remove the legacy GraphQL project

**Files:**
- Delete: `custom/backoffice/graphql/` (entire tree)
- Delete: `tests/tir/test_graphql_config.tir`, `tests/tir/test_graphql_errors.tir`, `tests/tir/test_graphql_modules.tir`, `tests/tir/test_graphql_playground.tir`, `tests/tir/test_graphql_sa1.tir`, `tests/tir/test_graphql_sb1.tir`
- Delete: `docs/api-reference.md`, `docs/architecture.md`, `docs/changelog.md`, `docs/configuration.md`, `docs/self-service-guide.md`
- Delete: `DEPLOY.md`, `README.md`
- Delete: `.superpowers/sdd/` (entire tree — task briefs/reports for the old project)
- Keep: `docs/superpowers/specs/`, `docs/superpowers/plans/` (this plan and the design spec)

**Interfaces:** None — this task produces no code, only a clean slate.

- [ ] **Step 1: Confirm working tree is clean before deleting**

Run: `git status --short`
Expected: empty output (no uncommitted changes). If not empty, stop and ask the user before proceeding — do not delete over unsaved work.

- [ ] **Step 2: Delete the legacy tree**

```bash
git rm -r custom/backoffice/graphql
git rm tests/tir/test_graphql_config.tir tests/tir/test_graphql_errors.tir tests/tir/test_graphql_modules.tir tests/tir/test_graphql_playground.tir tests/tir/test_graphql_sa1.tir tests/tir/test_graphql_sb1.tir
git rm docs/api-reference.md docs/architecture.md docs/changelog.md docs/configuration.md docs/self-service-guide.md
git rm DEPLOY.md README.md
git rm -r .superpowers/sdd
```

- [ ] **Step 3: Verify nothing of the old project remains**

Run: `git status --short && find custom tests/tir docs -maxdepth 2 -not -path '*/superpowers/*' 2>/dev/null`
Expected: `git status --short` shows only staged deletions (`D` entries); the `find` shows no `.tlpp`/`.tir`/legacy `.md` files left behind.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove legacy static-schema GraphQL project

Superseded by the dynamic dictionary-driven engine (see
docs/superpowers/specs/2026-08-13-graphql-core-engine-design.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Config loader and access control (deny-list + permission stub)

**Files:**
- Create: `custom/backoffice/graphql/config/graphql-config.json`
- Create: `custom/backoffice/graphql/core/config.tlpp`
- Create: `custom/backoffice/graphql/core/access-control.tlpp`

**Interfaces:**
- Consumes: nothing (first code in the new tree).
- Produces:
  - `GqlConfig():new() as object`
  - `GqlConfig():getDenyTables() as array` — array of character wildcard patterns
  - `GqlConfig():getDenyFields() as array` — array of character wildcard patterns
  - `GqlConfig():getDefaultPageSize() as numeric`
  - `GqlConfig():getMaxPageSize() as numeric`
  - `GqlConfig():getSchemaCacheTtlSeconds() as numeric`
  - `GqlConfig():MatchWildcard(cPattern as character, cValue as character) as logical` (static method)
  - `GqlAccessControl():new(oConfig as object) as object`
  - `GqlAccessControl():isTableAllowed(cTable as character) as logical`
  - `GqlAccessControl():isFieldAllowed(cTable as character, cField as character) as logical`
  - `GqlAccessControl():allowField(cTable as character, cField as character, oUserContext as object) as logical` — permission hook, always `.T.` in this sub-project

**Symbols to validate before compiling:** `MemoRead()`, `JsonObject():New()`/`:FromJson()`/`:toJson()`, `json[key]` bracket accessor, `FWLogMsg()` — all verified against the real running server, see the Global Constraints note on the JSON API.

- [ ] **Step 1: Create the config file**

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

- [ ] **Step 2: Write `core/config.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlConfig - loads custom/backoffice/graphql/config/graphql-config.json
      and exposes typed accessors for deny-lists and pagination limits.
/@*/
class GqlConfig
    private data aDenyTables         as array
    private data aDenyFields         as array
    private data nDefaultPageSize    as numeric
    private data nMaxPageSize        as numeric
    private data nSchemaCacheTtlSecs as numeric

    public method new() as object
    public method getDenyTables() as array
    public method getDenyFields() as array
    public method getDefaultPageSize() as numeric
    public method getMaxPageSize() as numeric
    public method getSchemaCacheTtlSeconds() as numeric
    static method MatchWildcard(cPattern as character, cValue as character) as logical
    static method SplitOnStar(cPattern as character) as array
endclass

method new() as object class GqlConfig
    local cPath    := "custom/backoffice/graphql/config/graphql-config.json" as character
    local cRaw     := "" as character
    local oJson    as json
    local oPag     as json
    local uParseResult

    ::aDenyTables         := {}
    ::aDenyFields         := {}
    ::nDefaultPageSize    := 20
    ::nMaxPageSize        := 200
    ::nSchemaCacheTtlSecs := 3600

    cRaw := MemoRead(cPath)
    if empty(cRaw)
        FWLogMsg("GqlConfig: " + cPath + " not found or empty, using built-in defaults", .F.)
        return self
    endif

    oJson := JsonObject():New()
    uParseResult := oJson:FromJson(cRaw)
    if valtype(uParseResult) != "U"
        FWLogMsg("GqlConfig: " + cPath + " is not valid JSON, using built-in defaults", .F.)
        return self
    endif

    if oJson["denyTables"] != nil
        ::aDenyTables := oJson["denyTables"]
    endif
    if oJson["denyFields"] != nil
        ::aDenyFields := oJson["denyFields"]
    endif
    if oJson["schemaCacheTtlSeconds"] != nil
        ::nSchemaCacheTtlSecs := oJson["schemaCacheTtlSeconds"]
    endif

    oPag := oJson["pagination"]
    if oPag != nil
        if oPag["defaultPageSize"] != nil
            ::nDefaultPageSize := oPag["defaultPageSize"]
        endif
        if oPag["maxPageSize"] != nil
            ::nMaxPageSize := oPag["maxPageSize"]
        endif
    endif

    return self
endmethod

method getDenyTables() as array class GqlConfig
    return ::aDenyTables
endmethod

method getDenyFields() as array class GqlConfig
    return ::aDenyFields
endmethod

method getDefaultPageSize() as numeric class GqlConfig
    return ::nDefaultPageSize
endmethod

method getMaxPageSize() as numeric class GqlConfig
    return ::nMaxPageSize
endmethod

method getSchemaCacheTtlSeconds() as numeric class GqlConfig
    return ::nSchemaCacheTtlSecs
endmethod

/*/{Protheus.doc}
@type Static Function
@author GraphQL Engine Team
@since 3.0.0
@param cPattern Character - wildcard pattern, "*" matches any run of characters
@param cValue Character - value to test
@return Logical - .T. if cValue matches cPattern
/@*/
method MatchWildcard(cPattern as character, cValue as character) as logical class GqlConfig
    local cUpValue   := upper(alltrim(cValue))   as character
    local cUpPattern := upper(alltrim(cPattern)) as character
    local aParts     := {}                        as array
    local cPart      := ""                         as character
    local nI         := 0                           as numeric
    local nSearchFrom := 1                            as numeric
    local nFoundAt    := 0                             as numeric
    local lStartsWithStar := (left(cUpPattern, 1) == "*") as logical
    local lEndsWithStar   := (right(cUpPattern, 1) == "*") as logical

    if !("*" $ cUpPattern)
        return cUpValue == cUpPattern
    endif

    aParts := GqlConfig():SplitOnStar(cUpPattern)

    for nI := 1 to len(aParts)
        cPart := aParts[nI]
        if empty(cPart)
            loop
        endif
        nFoundAt := at(cPart, substr(cUpValue, nSearchFrom))
        if nFoundAt == 0
            return .F.
        endif
        if nI == 1 .and. !lStartsWithStar .and. nFoundAt != 1
            return .F.
        endif
        nSearchFrom += (nFoundAt - 1) + len(cPart)
    next nI

    if !lEndsWithStar .and. nSearchFrom - 1 != len(cUpValue)
        return .F.
    endif

    return .T.
endmethod

method SplitOnStar(cPattern as character) as array class GqlConfig
    local aResult := {}          as array
    local cAccum  := ""           as character
    local nI      := 0             as numeric
    local cCh     := ""              as character

    for nI := 1 to len(cPattern)
        cCh := substr(cPattern, nI, 1)
        if cCh == "*"
            aAdd(aResult, cAccum)
            cAccum := ""
        else
            cAccum += cCh
        endif
    next nI
    aAdd(aResult, cAccum)

    return aResult
endmethod

endnamespace
```

- [ ] **Step 3: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/config.tlpp`
Expected: compile succeeds, `build/custom.rpo` updated, no errors in output.

- [ ] **Step 4: Write `core/access-control.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlAccessControl - deny-list (structural) + permission hook (per-user,
      wired to real auth in the Auth sub-project) access checks.
/@*/
class GqlAccessControl
    private data oConfig as object

    public method new(oConfig as object) as object
    public method isTableAllowed(cTable as character) as logical
    public method isFieldAllowed(cTable as character, cField as character) as logical
    public method allowField(cTable as character, cField as character, oUserContext as object) as logical
endclass

method new(oConfig as object) as object class GqlAccessControl
    ::oConfig := oConfig
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias, e.g. "SA1"
@return Logical - .T. unless cTable matches a denyTables pattern
/@*/
method isTableAllowed(cTable as character) as logical class GqlAccessControl
    local aDeny := ::oConfig:getDenyTables()
    local nI    := 0 as numeric

    for nI := 1 to len(aDeny)
        if GqlConfig():MatchWildcard(aDeny[nI], cTable)
            return .F.
        endif
    next nI
    return .T.
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias
@param cField Character - field name, e.g. "A1_COD"
@return Logical - .T. unless cField matches a denyFields pattern
/@*/
method isFieldAllowed(cTable as character, cField as character) as logical class GqlAccessControl
    local aDeny := ::oConfig:getDenyFields()
    local nI    := 0 as numeric

    for nI := 1 to len(aDeny)
        if GqlConfig():MatchWildcard(aDeny[nI], cField)
            return .F.
        endif
    next nI
    return .T.
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias
@param cField Character - field name
@param oUserContext Object - authenticated user context; nil until the
       Auth sub-project wires real authentication in
@return Logical - always .T. in this sub-project (extension point only)
@desc Single call site for per-user permission checks. Do not inline
      permission logic anywhere else — sub-project 3 (Auth) replaces
      only this method body.
/@*/
method allowField(cTable as character, cField as character, oUserContext as object) as logical class GqlAccessControl
    return .T.
endmethod

endnamespace
```

- [ ] **Step 5: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/access-control.tlpp`
Expected: compile succeeds, no errors.

- [ ] **Step 6: Commit**

```bash
git add custom/backoffice/graphql/config/graphql-config.json custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp
git commit -m "feat(graphql): add JSON config loader and deny-list access control

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Dictionary reader + lazy schema provider + introspection entry point

**Files:**
- Create: `custom/backoffice/graphql/core/dictionary-reader.tlpp`
- Create: `custom/backoffice/graphql/core/schema-provider.tlpp`
- Create: `custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp`
- Test: `tests/tir/test_graphql_introspection.tir`
- Test: `tests/tir/test_graphql_dynamic_type.tir`
- Test: `tests/tir/test_graphql_denylist.tir`

**Interfaces:**
- Consumes: `GqlConfig` (Task 2), `GqlAccessControl` (Task 2).
- Produces:
  - `GqlDictionaryReader():new(oAccessControl as object) as object`
  - `GqlDictionaryReader():listTables() as array` — array of JSON `{alias, name}`, deny-filtered
  - `GqlDictionaryReader():getTableFields(cTable as character) as array` — array of JSON `{name, graphqlType, sx3Type}`, deny + `X3_VISUAL` filtered
  - `GqlSchemaProvider():new(oDictionaryReader as object, oConfig as object) as object`
  - `GqlSchemaProvider():listTableNames() as array` — array of character, cached
  - `GqlSchemaProvider():getType(cTable as character) as json` — `{name, fields:[{name,type}]}`, lazy + cached, `nil` if table unknown/denied
  - `GqlSchemaProvider():reload()` — clears both caches
  - REST endpoint `GET /graphql` (empty/no `query` and no `type` param) → schema names only
  - REST endpoint `GET /graphql?type=<TABLE>` → full type detail for one table

**Symbols to validate before compiling:** `TCQuery ... New Alias &cAlias` (`topconn.ch`), `RetSqlName()`, `GetNextAlias()`, `dbGoTop()`/`dbSkip()`/`Eof()`/`dbCloseArea()` workarea navigation, `@Get` annotation + `oRest:getQueryRequest()`/`:setStatusResponse()` (`tlpp-rest.th`) — all verified against the real running server, see the Global Constraints notes on the JSON API, the REST entry point pattern, and SQL execution.

- [ ] **Step 1: Write the TIR tests first (they will fail — no endpoint exists yet)**

`tests/tir/test_graphql_introspection.tir`:
```python
"""
TIR Test — GraphQL schema introspection (table names only, deny-list applied)
"""
from contrib.tir import Webapp
import json


class TestGraphQLIntrospection:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_schema_lists_allowed_tables(self):
        result = self.client.http_get("/graphql")
        assert result.status_code == 200
        data = json.loads(result.text)
        assert "data" in data
        names = [t["name"] for t in data["data"]["__schema"]["types"]]
        assert "SA1" in names

    def test_schema_omits_denied_tables(self):
        result = self.client.http_get("/graphql")
        data = json.loads(result.text)
        names = [t["name"] for t in data["data"]["__schema"]["types"]]
        assert "SRA" not in names
        assert not any(n.startswith("SRH") for n in names)
```

`tests/tir/test_graphql_dynamic_type.tir`:
```python
"""
TIR Test — GraphQL dynamic type detail (SX3-driven), deny-list on fields
"""
from contrib.tir import Webapp
import json


class TestGraphQLDynamicType:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_type_reflects_real_sx3_fields(self):
        result = self.client.http_get("/graphql?type=SA1")
        assert result.status_code == 200
        data = json.loads(result.text)
        field_names = [f["name"] for f in data["data"]["__type"]["fields"]]
        assert "A1_COD" in field_names
        assert "A1_NOME" in field_names

    def test_type_omits_denied_fields(self):
        result = self.client.http_get("/graphql?type=SA1")
        data = json.loads(result.text)
        field_names = [f["name"] for f in data["data"]["__type"]["fields"]]
        assert not any("SENHA" in f for f in field_names)

    def test_unknown_or_denied_table_returns_error(self):
        result = self.client.http_get("/graphql?type=SRA")
        data = json.loads(result.text)
        assert "errors" in data
```

`tests/tir/test_graphql_denylist.tir`:
```python
"""
TIR Test — deny-list enforcement across introspection surfaces
"""
from contrib.tir import Webapp
import json


class TestGraphQLDenylist:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_denied_table_absent_from_schema_names(self):
        result = self.client.http_get("/graphql")
        data = json.loads(result.text)
        names = [t["name"] for t in data["data"]["__schema"]["types"]]
        assert "SR5" not in names

    def test_denied_table_type_lookup_errors(self):
        result = self.client.http_get("/graphql?type=SR5")
        data = json.loads(result.text)
        assert "errors" in data
```

- [ ] **Step 2: Write `core/dictionary-reader.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "topconn.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlDictionaryReader - raw read access to SX2 (tables) and SX3 (fields),
      filtered through GqlAccessControl. No caching here — caching is
      GqlSchemaProvider's job.
/@*/
class GqlDictionaryReader
    private data oAccessControl as object

    public method new(oAccessControl as object) as object
    public method listTables() as array
    public method getTableFields(cTable as character) as array
    public method mapScalarType(cSx3Type as character, nDecimal as numeric) as character
endclass

method new(oAccessControl as object) as object class GqlDictionaryReader
    ::oAccessControl := oAccessControl
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@return Array - JSON {alias, name} per allowed table, ordered by alias
/@*/
method listTables() as array class GqlDictionaryReader
    local aResult := {}     as array
    local cAlq    := GetNextAlias() as character
    local cQuery  := "SELECT X2_CHAVE AS TALIAS, X2_NOME AS TNOME FROM " + RetSqlName("SX2") + ;
                      " WHERE D_E_L_E_T_ = ' ' ORDER BY X2_CHAVE" as character
    local cAlias  := "" as character
    local oRow    as json

    TCQuery cQuery New Alias &cAlq
    (cAlq)->(dbGoTop())
    while !(cAlq)->(Eof())
        cAlias := alltrim((cAlq)->TALIAS)
        if ::oAccessControl:isTableAllowed(cAlias)
            oRow := JsonObject():New()
            oRow["alias"] := cAlias
            oRow["name"] := alltrim((cAlq)->TNOME)
            aAdd(aResult, oRow)
        endif
        (cAlq)->(dbSkip())
    enddo
    (cAlq)->(dbCloseArea())

    return aResult
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias, e.g. "SA1"
@return Array - JSON {name, sx3Type, graphqlType} per allowed, visible field
/@*/
method getTableFields(cTable as character) as array class GqlDictionaryReader
    local aResult  := {} as array
    local cAlq     := GetNextAlias() as character
    local cQuery   := "SELECT X3_CAMPO AS FCAMPO, X3_TIPO AS FTIPO, X3_DECIMAL AS FDECIMAL, X3_VISUAL AS FVISUAL" + ;
                       " FROM " + RetSqlName("SX3") + ;
                       " WHERE D_E_L_E_T_ = ' ' AND X3_ARQUIVO = '" + cTable + "' ORDER BY X3_ORDEM" as character
    local cField   := "" as character
    local oRow     as json

    if !::oAccessControl:isTableAllowed(cTable)
        return aResult
    endif

    TCQuery cQuery New Alias &cAlq
    (cAlq)->(dbGoTop())
    while !(cAlq)->(Eof())
        cField := alltrim((cAlq)->FCAMPO)
        if alltrim((cAlq)->FVISUAL) != "N" .and. ::oAccessControl:isFieldAllowed(cTable, cField)
            oRow := JsonObject():New()
            oRow["name"] := cField
            oRow["sx3Type"] := alltrim((cAlq)->FTIPO)
            oRow["graphqlType"] := ::mapScalarType(alltrim((cAlq)->FTIPO), (cAlq)->FDECIMAL)
            aAdd(aResult, oRow)
        endif
        (cAlq)->(dbSkip())
    enddo
    (cAlq)->(dbCloseArea())

    return aResult
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cSx3Type Character - SX3 X3_TIPO value (C/N/D/L/M)
@param nDecimal Numeric - SX3 X3_DECIMAL value
@return Character - GraphQL scalar name
/@*/
method mapScalarType(cSx3Type as character, nDecimal as numeric) as character class GqlDictionaryReader
    if cSx3Type == "N"
        if nDecimal == 0
            return "Int"
        endif
        return "Float"
    elseif cSx3Type == "L"
        return "Boolean"
    elseif cSx3Type == "D"
        return "String"
    elseif cSx3Type == "M"
        return "String"
    endif
    return "String"
endmethod

endnamespace
```

- [ ] **Step 3: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/dictionary-reader.tlpp`
Expected: compile succeeds.

- [ ] **Step 4: Write `core/schema-provider.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlSchemaProvider - lazy, TTL-cached GraphQL schema built from
      GqlDictionaryReader. Table names are cheap and cached eagerly on
      first listTableNames() call; full per-table types are generated
      only when getType() is called for that table.
/@*/
class GqlSchemaProvider
    private data oDictionaryReader as object
    private data oConfig           as object
    private data aTableNamesCache  as array
    private data hTypeCache        as json
    private data nCacheBuiltAt     as numeric

    public method new(oDictionaryReader as object, oConfig as object) as object
    public method listTableNames() as array
    public method getType(cTable as character) as json
    public method reload() as object
    method expireIfStale() as object
endclass

method new(oDictionaryReader as object, oConfig as object) as object class GqlSchemaProvider
    ::oDictionaryReader := oDictionaryReader
    ::oConfig           := oConfig
    ::aTableNamesCache  := nil
    ::hTypeCache        := JsonObject():New()
    ::nCacheBuiltAt      := 0
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@return Array - allowed table aliases, cached
/@*/
method listTableNames() as array class GqlSchemaProvider
    local aTables := {} as array
    local nI      := 0    as numeric

    ::expireIfStale()

    if ::aTableNamesCache == nil
        aTables := ::oDictionaryReader:listTables()
        ::aTableNamesCache := {}
        for nI := 1 to len(aTables)
            aAdd(::aTableNamesCache, aTables[nI]["alias"])
        next nI
        if ::nCacheBuiltAt == 0
            ::nCacheBuiltAt := seconds()
        endif
    endif

    return ::aTableNamesCache
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias
@return JSON - {name, fields:[{name,type}]}, or nil if unknown/denied
/@*/
method getType(cTable as character) as json class GqlSchemaProvider
    local aNames  := ::listTableNames()
    local oType   as json
    local aFields as array
    local nI      := 0 as numeric

    if ascan(aNames, {|c| c == cTable}) == 0
        return nil
    endif

    if ::hTypeCache[cTable] != nil
        return ::hTypeCache[cTable]
    endif

    aFields := ::oDictionaryReader:getTableFields(cTable)
    oType   := JsonObject():New()
    oType["name"] := cTable
    oType["fields"] := aFields
    oType["relations"] := {}

    ::hTypeCache[cTable] := oType
    return oType
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@desc Clears both caches. Call after dictionary changes, or let TTL expire.
/@*/
method reload() as object class GqlSchemaProvider
    ::aTableNamesCache := nil
    ::hTypeCache        := JsonObject():New()
    ::nCacheBuiltAt      := 0
    return self
endmethod

method expireIfStale() as object class GqlSchemaProvider
    local nTtl := ::oConfig:getSchemaCacheTtlSeconds()
    if ::nCacheBuiltAt > 0 .and. (seconds() - ::nCacheBuiltAt) > nTtl
        ::reload()
    endif
    return self
endmethod

endnamespace
```

- [ ] **Step 5: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/schema-provider.tlpp`
Expected: compile succeeds.

- [ ] **Step 6: Write `entrypoints/service.entrypoint.tlpp` (introspection paths only — `query` param wired in Task 9)**

```tlpp
#include "tlpp-core.th"
#include "tlpp-rest.th"
#include "totvs.ch"

/*/{Protheus.doc}
GQLSERVICE
Dynamic GraphQL REST endpoint over the Protheus data dictionary.
GET /rest/graphql              -> schema type names (deny-list applied)
GET /rest/graphql?type=<TABLE> -> full type detail for one table
GET /rest/graphql?query=<...>  -> full query execution (Task 9)
@type User Function
@author GraphQL Engine Team
@since 3.0.0
@return Logical - .T.
/*/
@Get("/graphql")
User Function GQLSERVICE() as logical
    local oConfig    := custom.backoffice.graphql.GqlConfig():new()             as object
    local oAccess    := custom.backoffice.graphql.GqlAccessControl():new(oConfig) as object
    local oDict      := custom.backoffice.graphql.GqlDictionaryReader():new(oAccess) as object
    local oSchema    := custom.backoffice.graphql.GqlSchemaProvider():new(oDict, oConfig) as object
    local jParams    as json
    local cQuery     := "" as character
    local cTypeName  := "" as character
    local oResult    as json

    jParams   := oRest:getQueryRequest()
    cQuery    := jParams:GetJsonText("query")
    cTypeName := jParams:GetJsonText("type")
    if cQuery == "null"
        cQuery := ""
    endif
    if cTypeName == "null"
        cTypeName := ""
    endif

    if !empty(cQuery)
        // Wired in Task 9 (full parse/validate/execute pipeline).
        oResult := custom.backoffice.graphql.GqlErrors():single("query execution not available yet")
    elseif !empty(cTypeName)
        oResult := custom.backoffice.graphql.GqlIntrospection():typeDetail(oSchema, cTypeName)
    else
        oResult := custom.backoffice.graphql.GqlIntrospection():schemaNames(oSchema)
    endif

    oRest:setStatusResponse(200, oResult:toJson())

Return .T.
```

Note: `oRest` is not declared with `local` — it is injected into scope by the `@Get` REST framework for any function it annotates, matching this environment's own working REST examples. Declaring `local oRest` would shadow it and break the endpoint.

- [ ] **Step 7: Write the small introspection + error helpers the entry point calls**

Add to `core/schema-provider.tlpp` (same namespace, new file so the entry point's includes stay focused): create `custom/backoffice/graphql/core/introspection.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlIntrospection - builds the __schema/__type response envelopes.
/@*/
class GqlIntrospection
    static method schemaNames(oSchemaProvider as object) as json
    static method typeDetail(oSchemaProvider as object, cTable as character) as json
endclass

method schemaNames(oSchemaProvider as object) as json class GqlIntrospection
    local aNames := oSchemaProvider:listTableNames() as array
    local aTypes := {}                                 as array
    local nI     := 0                                    as numeric
    local oData  := JsonObject():New()                        as json
    local oSchema := JsonObject():New()                         as json
    local oQType  := JsonObject():New()                          as json
    local oType   as json
    local oResult as json

    for nI := 1 to len(aNames)
        oType := JsonObject():New()
        oType["name"] := aNames[nI]
        aAdd(aTypes, oType)
    next nI

    oQType["name"] := "Query"
    oSchema["queryType"] := oQType
    oSchema["types"] := aTypes
    oData["__schema"] := oSchema

    oResult := JsonObject():New()
    oResult["data"] := oData
    return oResult
endmethod

method typeDetail(oSchemaProvider as object, cTable as character) as json class GqlIntrospection
    local oType := oSchemaProvider:getType(upper(alltrim(cTable))) as json
    local oData as json
    local oResult as json

    if oType == nil
        return GqlErrors():single("Unknown or restricted type: " + cTable)
    endif

    oData := JsonObject():New()
    oData["__type"] := oType

    oResult := JsonObject():New()
    oResult["data"] := oData
    return oResult
endmethod

endnamespace
```

Create `custom/backoffice/graphql/core/errors.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlErrors - builds the {"errors":[{"message":...}]} response envelope.
/@*/
class GqlErrors
    static method single(cMessage as character) as json
    static method fromArray(aMessages as array) as json
endclass

method single(cMessage as character) as json class GqlErrors
    return GqlErrors():fromArray({cMessage})
endmethod

method fromArray(aMessages as array) as json class GqlErrors
    local aErrors := {} as array
    local nI      := 0    as numeric
    local oErr    as json
    local oResult as json

    for nI := 1 to len(aMessages)
        oErr := JsonObject():New()
        oErr["message"] := aMessages[nI]
        aAdd(aErrors, oErr)
    next nI

    oResult := JsonObject():New()
    oResult["errors"] := aErrors
    return oResult
endmethod

endnamespace
```

No entry point include changes needed — `GqlIntrospection` and `GqlErrors`
become available once their `.tlpp` files are compiled into the same RPO
(see the Global Constraints note on cross-file `#include`).

- [ ] **Step 8: Compile everything and deploy**

```bash
compile.sh custom/backoffice/graphql/core/introspection.tlpp
compile.sh custom/backoffice/graphql/core/errors.tlpp
compile.sh custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
deploy-rpo.sh
```
Expected: all compiles succeed, RPO deployed.

- [ ] **Step 9: Run the TIR tests to verify they now pass**

Run: `pytest tests/tir/test_graphql_introspection.tir tests/tir/test_graphql_dynamic_type.tir tests/tir/test_graphql_denylist.tir -v`
Expected: all pass. If `test_type_reflects_real_sx3_fields` fails because SA1 isn't in this environment's dictionary, substitute a table alias confirmed present via `execute-sql`/`list-objects` MCP before editing the test.

- [ ] **Step 10: Commit**

```bash
git add custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp custom/backoffice/graphql/core/introspection.tlpp custom/backoffice/graphql/core/errors.tlpp custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp tests/tir/test_graphql_introspection.tir tests/tir/test_graphql_dynamic_type.tir tests/tir/test_graphql_denylist.tir
git commit -m "feat(graphql): dynamic schema introspection over SX2/SX3

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: SX9-driven relationships in the schema

**Files:**
- Modify: `custom/backoffice/graphql/core/dictionary-reader.tlpp` (add `getRelations`)
- Modify: `custom/backoffice/graphql/core/schema-provider.tlpp` (populate `relations` in `getType`)
- Modify: `tests/tir/test_graphql_dynamic_type.tir` (add a relations assertion)

**Interfaces:**
- Consumes: `GqlAccessControl:isTableAllowed` (Task 2).
- Produces: `GqlDictionaryReader():getRelations(cTable as character) as array` — array of JSON `{relatedTable, localFields, foreignFields, cardinality}`, where `cardinality` is `"ONE"` or `"MANY"` from `X9_LIGCDOM`. `getType()`'s `relations` field is now populated as `[{name, type, cardinality}]`.

**Symbols to validate before compiling:** exact SX9 field names (`X9_DOM`, `X9_CDOM`, `X9_EXPDOM`, `X9_EXPCDOM`, `X9_LIGDOM`, `X9_LIGCDOM`) against `execute-sql`/`get-object-details` for this environment's SX9 layout — confirm before compiling, the user supplied these names from memory during brainstorming and they should be checked against the live dictionary.

- [ ] **Step 1: Add a relations assertion to the existing dynamic-type test**

Append to `TestGraphQLDynamicType` in `tests/tir/test_graphql_dynamic_type.tir`:
```python
    def test_type_exposes_sx9_relations(self):
        result = self.client.http_get("/graphql?type=SA1")
        data = json.loads(result.text)
        relation_names = [r["name"] for r in data["data"]["__type"]["relations"]]
        assert isinstance(relation_names, list)
```

Note: this assertion is intentionally structural (relations is always a list) rather than asserting a specific related table name, since SX9 content is environment-specific. If this environment's SX9 defines a known SA1→SC5 rule, strengthen the assertion to `assert "SC5" in relation_names` after confirming it via `execute-sql`.

- [ ] **Step 2: Run the test to see it still passes trivially (relations already `[]`) — confirms the harness before the real change**

Run: `pytest tests/tir/test_graphql_dynamic_type.tir::TestGraphQLDynamicType::test_type_exposes_sx9_relations -v`
Expected: PASS (relations is `[]`, which is a list).

- [ ] **Step 3: Add `getRelations` to `core/dictionary-reader.tlpp`**

TLPP requires the method signature to be declared inside `class...endclass` and
implemented separately outside it. Add the declaration line to the existing
`class GqlDictionaryReader ... endclass` block (alongside the other `public method`
lines):

```tlpp
    public method getRelations(cTable as character) as array
```

Then add the implementation below the class's other method implementations
(after `mapScalarType`'s `endmethod`, before `endnamespace`):

```tlpp
/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias, e.g. "SA1"
@return Array - JSON {relatedTable, localFields, foreignFields, cardinality}
        per SX9 rule where cTable is the origin (X9_DOM) and the
        destination table is itself allowed.
/@*/
method getRelations(cTable as character) as array class GqlDictionaryReader
    local aResult := {} as array
    local cAlq    := GetNextAlias() as character
    local cSx9Table := RetSqlName("SX9") as character
    local cQuery  := "" as character
    local cRelated := "" as character
    local oRow     as json
    local cCardinality := "" as character

    if empty(cSx9Table)
        // ponytail: SX9 not registered in every Protheus deployment (confirmed
        // empty RetSqlName against the live server this plan was verified
        // against) - degrade to "no relations" instead of a malformed query.
        return aResult
    endif

    cQuery := "SELECT X9_CDOM AS RTABLE, X9_EXPDOM AS RLOCAL, X9_EXPCDOM AS RFOREIGN, X9_LIGCDOM AS RCARD" + ;
               " FROM " + cSx9Table + ;
               " WHERE D_E_L_E_T_ = ' ' AND X9_DOM = '" + cTable + "'"

    TCQuery cQuery New Alias &cAlq
    (cAlq)->(dbGoTop())
    while !(cAlq)->(Eof())
        cRelated := alltrim((cAlq)->RTABLE)
        if ::oAccessControl:isTableAllowed(cRelated)
            cCardinality := "MANY"
            if alltrim((cAlq)->RCARD) == "1"
                cCardinality := "ONE"
            endif
            oRow := JsonObject():New()
            oRow["relatedTable"] := cRelated
            oRow["localFields"] := alltrim((cAlq)->RLOCAL)
            oRow["foreignFields"] := alltrim((cAlq)->RFOREIGN)
            oRow["cardinality"] := cCardinality
            aAdd(aResult, oRow)
        endif
        (cAlq)->(dbSkip())
    enddo
    (cAlq)->(dbCloseArea())

    return aResult
endmethod
```

- [ ] **Step 4: Wire relations into `getType()` in `core/schema-provider.tlpp`**

`getType()`'s `local` declarations must all stay at the top of the method
(this project's TLPP convention forbids a `local` after executable
statements — it is a compile error, C2051). Add these four to the
existing top-of-method `local` block (alongside `aNames`, `oType`,
`aFields`, `nI`):
```tlpp
    local aRelations := {} as array
    local aRelationSummary := {} as array
    local nJ := 0 as numeric
    local oRel as json
    local cRelType := "" as character
```

Then replace `oType["relations"] := {}` with (no `local` keywords here — they're all declared above now):
```tlpp
        aRelations := ::oDictionaryReader:getRelations(cTable)

        for nJ := 1 to len(aRelations)
            cRelType := aRelations[nJ]["relatedTable"]
            if aRelations[nJ]["cardinality"] == "MANY"
                cRelType := "[" + aRelations[nJ]["relatedTable"] + "]"
            endif
            oRel := JsonObject():New()
            oRel["name"] := aRelations[nJ]["relatedTable"]
            oRel["type"] := cRelType
            oRel["cardinality"] := aRelations[nJ]["cardinality"]
            aAdd(aRelationSummary, oRel)
        next nJ

        oType["relations"] := aRelationSummary
```

- [ ] **Step 5: Compile and deploy**

```bash
compile.sh custom/backoffice/graphql/core/dictionary-reader.tlpp
compile.sh custom/backoffice/graphql/core/schema-provider.tlpp
deploy-rpo.sh
```
Expected: compiles succeed.

- [ ] **Step 6: Run the dynamic-type tests again**

Run: `pytest tests/tir/test_graphql_dynamic_type.tir -v`
Expected: all pass, including `test_type_exposes_sx9_relations`, now backed by real SX9 data.

- [ ] **Step 7: Commit**

```bash
git add custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp tests/tir/test_graphql_dynamic_type.tir
git commit -m "feat(graphql): expose SX9 relationships in the dynamic type schema

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Lexer (GraphQL tokenizer)

**Files:**
- Create: `custom/backoffice/graphql/core/lexer.tlpp`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `GqlLexer():new(cSource as character) as object`
  - `GqlLexer():nextToken() as json` — advances and returns `{kind, value}`; `kind` in `"NAME"`, `"INT"`, `"FLOAT"`, `"STRING"`, `"PUNCT"`, `"EOF"`
  - `GqlLexer():peek() as json` — same shape, does not advance

**Symbols to validate before compiling:** none beyond core AdvPL string functions (`substr`, `chr`, `val`) already used in the deleted project's parser — these are core language, not framework, so no MCP lookup needed.

- [ ] **Step 1: Write `core/lexer.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlLexer - tokenizes GraphQL query text into {kind, value} tokens.
      kind: NAME, INT, FLOAT, STRING, PUNCT, EOF.
/@*/
class GqlLexer
    private data cSource     as character
    private data nPos        as numeric
    private data nLen        as numeric
    private data oPeeked     as json

    public method new(cSource as character) as object
    public method peek() as json
    public method nextToken() as json
    method skipIgnored() as object
    method scan() as json
    method scanName() as json
    method scanString() as json
    method scanNumber() as json
    method makeToken(cKind as character, cValue as character) as json
endclass

method new(cSource as character) as object class GqlLexer
    ::cSource := cSource
    ::nPos    := 1
    ::nLen    := len(cSource)
    ::oPeeked := nil
    return self
endmethod

method peek() as json class GqlLexer
    if ::oPeeked == nil
        ::oPeeked := ::scan()
    endif
    return ::oPeeked
endmethod

method nextToken() as json class GqlLexer
    local oTok := ::peek() as json
    ::oPeeked := nil
    return oTok
endmethod

method skipIgnored() as object class GqlLexer
    local cCh := "" as character
    while ::nPos <= ::nLen
        cCh := substr(::cSource, ::nPos, 1)
        if cCh == " " .or. cCh == chr(9) .or. cCh == chr(10) .or. cCh == chr(13) .or. cCh == ","
            ::nPos++
        elseif cCh == "#"
            while ::nPos <= ::nLen .and. substr(::cSource, ::nPos, 1) != chr(10)
                ::nPos++
            enddo
        else
            exit
        endif
    enddo
    return self
endmethod

method scan() as json class GqlLexer
    local cCh   := "" as character
    local oTok  as json

    ::skipIgnored()

    if ::nPos > ::nLen
        return ::makeToken("EOF", "")
    endif

    cCh := substr(::cSource, ::nPos, 1)

    if (cCh >= "a" .and. cCh <= "z") .or. (cCh >= "A" .and. cCh <= "Z") .or. cCh == "_"
        return ::scanName()
    elseif cCh == '"'
        return ::scanString()
    elseif (cCh >= "0" .and. cCh <= "9") .or. cCh == "-"
        return ::scanNumber()
    endif

    ::nPos++
    return ::makeToken("PUNCT", cCh)
endmethod

method scanName() as json class GqlLexer
    local nStart := ::nPos as numeric
    local cCh    := "" as character

    while ::nPos <= ::nLen
        cCh := substr(::cSource, ::nPos, 1)
        if (cCh >= "a" .and. cCh <= "z") .or. (cCh >= "A" .and. cCh <= "Z") .or. (cCh >= "0" .and. cCh <= "9") .or. cCh == "_"
            ::nPos++
        else
            exit
        endif
    enddo

    return ::makeToken("NAME", substr(::cSource, nStart, ::nPos - nStart))
endmethod

method scanString() as json class GqlLexer
    local cResult := "" as character
    local cCh     := "" as character

    ::nPos++ // opening quote
    while ::nPos <= ::nLen
        cCh := substr(::cSource, ::nPos, 1)
        if cCh == '"'
            ::nPos++
            return ::makeToken("STRING", cResult)
        elseif cCh == '\'
            ::nPos++
            cCh := substr(::cSource, ::nPos, 1)
            if cCh == "n"
                cResult += chr(10)
            elseif cCh == "t"
                cResult += chr(9)
            else
                cResult += cCh
            endif
            ::nPos++
        else
            cResult += cCh
            ::nPos++
        endif
    enddo

    return ::makeToken("STRING", cResult) // unterminated: parser reports the error
endmethod

method scanNumber() as json class GqlLexer
    local nStart  := ::nPos as numeric
    local lFloat  := .F.     as logical
    local cCh     := ""       as character
    local cKind   := "INT"     as character

    if substr(::cSource, ::nPos, 1) == "-"
        ::nPos++
    endif
    while ::nPos <= ::nLen
        cCh := substr(::cSource, ::nPos, 1)
        if cCh >= "0" .and. cCh <= "9"
            ::nPos++
        elseif cCh == "." .and. !lFloat
            lFloat := .T.
            ::nPos++
        else
            exit
        endif
    enddo

    if lFloat
        cKind := "FLOAT"
    endif

    return ::makeToken(cKind, substr(::cSource, nStart, ::nPos - nStart))
endmethod

method makeToken(cKind as character, cValue as character) as json class GqlLexer
    local oTok := JsonObject():New() as json
    oTok["kind"] := cKind
    oTok["value"] := cValue
    return oTok
endmethod

endnamespace
```

- [ ] **Step 2: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/lexer.tlpp`
Expected: compile succeeds. (No TIR test yet — the lexer has no HTTP surface until the parser and executor exist; see Global Constraints on test strategy.)

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/lexer.tlpp
git commit -m "feat(graphql): add GraphQL query tokenizer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Parser (tokens → AST)

**Files:**
- Create: `custom/backoffice/graphql/core/parser.tlpp`

**Interfaces:**
- Consumes: `GqlLexer():new/nextToken/peek` (Task 5).
- Produces:
  - `GqlParser():new(cSource as character) as object`
  - `GqlParser():parse() as json` — returns `{kind:"Document", definitions:[...]}` AST, or `nil` if there were errors
  - `GqlParser():getErrors() as array` — array of character error messages

AST shapes produced (consumed by Task 7/8):
- OperationDefinition: `{kind, operation, selectionSet: [Field...]}`
- Field: `{kind:"Field", name, alias?, arguments: {argName: ValueNode}, selectionSet?: [Field...]}`
- ValueNode: `{kind: "StringValue"|"IntValue"|"FloatValue"|"BooleanValue"|"NullValue"|"ListValue"|"ObjectValue", value}`

**Symbols to validate before compiling:** none beyond core language — pure AST construction, no framework calls.

- [ ] **Step 1: Write `core/parser.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlParser - recursive-descent parser building a GraphQL AST (as JSON)
      from a GqlLexer token stream.
/@*/
class GqlParser
    private data oLexer  as object
    private data aErrors as array

    public method new(cSource as character) as object
    public method getErrors() as array
    public method parse() as json
    method parseOperation() as json
    method parseSelectionSet() as array
    method parseField() as json
    method parseArguments() as json
    method parseValue() as json
    method parseValueList() as array
    method parseObjectValue() as json
    method expectPunct(cExpected as character) as logical
endclass

method new(cSource as character) as object class GqlParser
    ::oLexer  := GqlLexer():new(cSource)
    ::aErrors := {}
    return self
endmethod

method getErrors() as array class GqlParser
    return ::aErrors
endmethod

method parse() as json class GqlParser
        local aDefs := {} as array
        local oDoc  as json

        while ::oLexer:peek()["kind"] != "EOF"
            aAdd(aDefs, ::parseOperation())
            if len(::aErrors) > 0
                return nil
            endif
        enddo

        oDoc := JsonObject():New()
        oDoc["kind"] := "Document"
        oDoc["definitions"] := aDefs
        return oDoc
    endmethod

    method parseOperation() as json class GqlParser
        local oTok  := ::oLexer:peek() as json
        local cOp   := "query" as character
        local oOp   as json

        if oTok["kind"] == "NAME" .and. (oTok["value"] == "query" .or. oTok["value"] == "mutation")
            cOp := oTok["value"]
            ::oLexer:nextToken()
            oTok := ::oLexer:peek()
            if oTok["kind"] == "NAME"
                ::oLexer:nextToken() // optional operation name, discarded (not needed by the executor)
            endif
        endif

        oOp := JsonObject():New()
        oOp["kind"] := "OperationDefinition"
        oOp["operation"] := cOp
        oOp["selectionSet"] := ::parseSelectionSet()
        return oOp
    endmethod

    method parseSelectionSet() as array class GqlParser
        local aFields := {} as array

        if !::expectPunct("{")
            return aFields
        endif

        while ::oLexer:peek()["kind"] != "EOF" .and. !(::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == "}")
            aAdd(aFields, ::parseField())
            if len(::aErrors) > 0
                return aFields
            endif
        enddo

        ::expectPunct("}")
        return aFields
    endmethod

    method parseField() as json class GqlParser
        local oTok    := ::oLexer:nextToken() as json
        local cName1  := "" as character
        local cAlias  := "" as character
        local oField  as json
        local oArgs   as json

        if oTok["kind"] != "NAME"
            aAdd(::aErrors, "Expected field name, found '" + oTok["value"] + "'")
            return nil
        endif
        cName1 := oTok["value"]
        cAlias := cName1

        if ::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == ":"
            ::oLexer:nextToken()
            oTok := ::oLexer:nextToken()
            cAlias := cName1
            cName1 := oTok["value"]
        endif

        oArgs := JsonObject():New()
        if ::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == "("
            oArgs := ::parseArguments()
            if len(::aErrors) > 0
                return nil
            endif
        endif

        oField := JsonObject():New()
        oField["kind"] := "Field"
        oField["name"] := cName1
        if cAlias != cName1
            oField["alias"] := cAlias
        endif
        oField["arguments"] := oArgs

        if ::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == "{"
            oField["selectionSet"] := ::parseSelectionSet()
        endif

        return oField
    endmethod

    method parseArguments() as json class GqlParser
        local oArgs := JsonObject():New() as json
        local cName := "" as character
        local oTok  as json

        ::expectPunct("(")
        while ::oLexer:peek()["kind"] != "EOF" .and. !(::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == ")")
            oTok := ::oLexer:nextToken()
            if oTok["kind"] != "NAME"
                aAdd(::aErrors, "Expected argument name, found '" + oTok["value"] + "'")
                return oArgs
            endif
            cName := oTok["value"]
            if !::expectPunct(":")
                return oArgs
            endif
            oArgs[cName] := ::parseValue()
            if len(::aErrors) > 0
                return oArgs
            endif
        enddo
        ::expectPunct(")")

        return oArgs
    endmethod

    method parseValue() as json class GqlParser
        local oTok := ::oLexer:nextToken() as json
        local oVal as json

        oVal := JsonObject():New()

        if oTok["kind"] == "STRING"
            oVal["kind"] := "StringValue"
            oVal["value"] := oTok["value"]
        elseif oTok["kind"] == "INT"
            oVal["kind"] := "IntValue"
            oVal["value"] := val(oTok["value"])
        elseif oTok["kind"] == "FLOAT"
            oVal["kind"] := "FloatValue"
            oVal["value"] := val(oTok["value"])
        elseif oTok["kind"] == "NAME" .and. oTok["value"] == "true"
            oVal["kind"] := "BooleanValue"
            oVal["value"] := .T.
        elseif oTok["kind"] == "NAME" .and. oTok["value"] == "false"
            oVal["kind"] := "BooleanValue"
            oVal["value"] := .F.
        elseif oTok["kind"] == "NAME" .and. oTok["value"] == "null"
            oVal["kind"] := "NullValue"
        elseif oTok["kind"] == "PUNCT" .and. oTok["value"] == "["
            oVal["kind"] := "ListValue"
            oVal["value"] := ::parseValueList()
        elseif oTok["kind"] == "PUNCT" .and. oTok["value"] == "{"
            oVal["kind"] := "ObjectValue"
            oVal["value"] := ::parseObjectValue()
        else
            aAdd(::aErrors, "Unexpected value token: '" + oTok["value"] + "'")
        endif

        return oVal
    endmethod

    method parseValueList() as array class GqlParser
        local aVals := {} as array
        while ::oLexer:peek()["kind"] != "EOF" .and. !(::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == "]")
            aAdd(aVals, ::parseValue())
            if len(::aErrors) > 0
                return aVals
            endif
        enddo
        ::expectPunct("]")
        return aVals
    endmethod

    method parseObjectValue() as json class GqlParser
        local oObj  := JsonObject():New() as json
        local cName := "" as character
        local oTok  as json

        while ::oLexer:peek()["kind"] != "EOF" .and. !(::oLexer:peek()["kind"] == "PUNCT" .and. ::oLexer:peek()["value"] == "}")
            oTok := ::oLexer:nextToken()
            if oTok["kind"] != "NAME"
                aAdd(::aErrors, "Expected field name in object value, found '" + oTok["value"] + "'")
                return oObj
            endif
            cName := oTok["value"]
            if !::expectPunct(":")
                return oObj
            endif
            oObj[cName] := ::parseValue()
            if len(::aErrors) > 0
                return oObj
            endif
        enddo
        ::expectPunct("}")

        return oObj
    endmethod

    method expectPunct(cExpected as character) as logical class GqlParser
        local oTok := ::oLexer:nextToken() as json
        if oTok["kind"] != "PUNCT" .or. oTok["value"] != cExpected
            aAdd(::aErrors, "Expected '" + cExpected + "' but found '" + oTok["value"] + "'")
            return .F.
        endif
        return .T.
    endmethod

endnamespace
```

- [ ] **Step 2: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/parser.tlpp`
Expected: compile succeeds. (Still no HTTP surface — wired in Task 9.)

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/parser.tlpp
git commit -m "feat(graphql): add recursive-descent GraphQL parser (tokens to AST)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Validator (AST vs dynamic schema)

**Files:**
- Create: `custom/backoffice/graphql/core/validator.tlpp`

**Interfaces:**
- Consumes: `GqlSchemaProvider():listTableNames/getType` (Task 3/4), AST shapes from Task 6.
- Produces:
  - `GqlValidator():new(oSchemaProvider as object) as object`
  - `GqlValidator():validate(oDocument as json) as array` — array of character error messages, empty if valid. Checks: root field name is a known table; each requested scalar sub-field exists on that table's type OR matches a relation name (nested selection only valid for relation fields); `filter` argument items reference existing scalar fields and a supported operator (`eq`,`gt`,`gte`,`lt`,`lte`).

**Symbols to validate before compiling:** none beyond core language — pure logic over the AST/schema JSON already defined.

- [ ] **Step 1: Write `core/validator.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlValidator - validates a parsed AST against the dynamic schema
      before execution: unknown tables, unknown fields, unsupported filter
      operators.
/@*/
class GqlValidator
    private data oSchemaProvider as object

    public method new(oSchemaProvider as object) as object
    public method validate(oDocument as json) as array
    method validateRootField(oField as json, aErrors as array) as object
    method validateSelection(oType as json, aSelection as array, aErrors as array) as object
    method fieldExistsOnType(oType as json, cField as character) as logical
    method relationTargetType(oType as json, cField as character) as json
    method validateArguments(oType as json, oArgs as json, aErrors as array) as object
endclass

method new(oSchemaProvider as object) as object class GqlValidator
    ::oSchemaProvider := oSchemaProvider
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param oDocument JSON - Document AST from GqlParser:parse()
@return Array - error messages, empty if the document is valid
/@*/
method validate(oDocument as json) as array class GqlValidator
        local aErrors := {} as array
        local aDefs   := oDocument["definitions"] as array
        local nI      := 0 as numeric
        local aSel    as array
        local nJ      := 0 as numeric

        for nI := 1 to len(aDefs)
            aSel := aDefs[nI]["selectionSet"]
            for nJ := 1 to len(aSel)
                ::validateRootField(aSel[nJ], aErrors)
            next nJ
        next nI

        return aErrors
    endmethod

    method validateRootField(oField as json, aErrors as array) as object class GqlValidator
        local cTable := oField["name"] as character
        local oType  := ::oSchemaProvider:getType(cTable) as json
        local aSubSel as array

        if oType == nil
            aAdd(aErrors, "Unknown or restricted table: '" + cTable + "'")
            return self
        endif

        ::validateArguments(oType, oField["arguments"], aErrors)

        aSubSel := oField["selectionSet"]
        if aSubSel == nil
            aAdd(aErrors, "Field '" + cTable + "' requires a selection of sub-fields")
            return self
        endif
        ::validateSelection(oType, aSubSel, aErrors)
        return self
    endmethod

    method validateSelection(oType as json, aSelection as array, aErrors as array) as object class GqlValidator
        local nI       := 0 as numeric
        local oField   as json
        local cName    as character
        local oRelType as json

        for nI := 1 to len(aSelection)
            oField := aSelection[nI]
            cName  := oField["name"]

            if ::fieldExistsOnType(oType, cName)
                loop
            endif

            oRelType := ::relationTargetType(oType, cName)
            if oRelType != nil
                if oField["selectionSet"] == nil
                    aAdd(aErrors, "Relation field '" + cName + "' requires a selection of sub-fields")
                else
                    ::validateSelection(oRelType, oField["selectionSet"], aErrors)
                endif
                loop
            endif

            aAdd(aErrors, "Unknown field '" + cName + "' on type '" + oType["name"] + "'")
        next nI
        return self
    endmethod

    method fieldExistsOnType(oType as json, cField as character) as logical class GqlValidator
        local aFields := oType["fields"] as array
        local nI      := 0 as numeric

        for nI := 1 to len(aFields)
            if aFields[nI]["name"] == cField
                return .T.
            endif
        next nI
        return .F.
    endmethod

    method relationTargetType(oType as json, cField as character) as json class GqlValidator
        local aRelations := oType["relations"] as array
        local nI         := 0 as numeric

        for nI := 1 to len(aRelations)
            if aRelations[nI]["name"] == cField
                return ::oSchemaProvider:getType(cField)
            endif
        next nI
        return nil
    endmethod

    method validateArguments(oType as json, oArgs as json, aErrors as array) as object class GqlValidator
        local oFilterArg := oArgs["filter"] as json
        local aFilters   := {} as array
        local nI       := 0 as numeric
        local oFilter   as json
        local aValidOps := {"eq", "gt", "gte", "lt", "lte"} as array

        if oFilterArg == nil
            return self
        endif
        aFilters := oFilterArg["value"]
        if valtype(aFilters) != "A"
            aAdd(aErrors, "Argument 'filter' must be a list")
            return self
        endif

        for nI := 1 to len(aFilters)
            oFilter := aFilters[nI]["value"]
            if oFilter["field"] == nil .or. oFilter["op"] == nil .or. oFilter["value"] == nil
                aAdd(aErrors, "Each filter item requires field, op and value")
                loop
            endif
            if !::fieldExistsOnType(oType, oFilter["field"]["value"])
                aAdd(aErrors, "Unknown filter field '" + oFilter["field"]["value"] + "' on type '" + oType["name"] + "'")
            endif
            if ascan(aValidOps, {|c| c == oFilter["op"]["value"]}) == 0
                aAdd(aErrors, "Unsupported filter operator '" + oFilter["op"]["value"] + "'")
            endif
        next nI
        return self
    endmethod

endnamespace
```

- [ ] **Step 2: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/validator.tlpp`
Expected: compile succeeds.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/validator.tlpp
git commit -m "feat(graphql): add AST validator against the dynamic schema

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Query builder (AST → bound SQL, pagination, filters, mandatory guards)

**Files:**
- Create: `custom/backoffice/graphql/core/query-builder.tlpp`
- Modify: `custom/backoffice/graphql/core/dictionary-reader.tlpp` (add `getOrderKey`, used for stable pagination ordering)

**Interfaces:**
- Consumes: `GqlConfig` (Task 2), AST field/arguments shape (Task 6).
- Produces:
  - `GqlDictionaryReader():getOrderKey(cTable as character) as character` — comma-joined field list of SIX order `1` for `cTable` (falls back to the table's first scalar field if no SIX row exists)
  - `GqlDictionaryReader():getFilialField(cTable as character) as character` — the real branch field name for `cTable` (e.g. `A1_FILIAL` for `SA1`), read from SX3 by suffix match. **Not** `cTable + "_FILIAL"` — verified against the live server that the field prefix and the table alias differ (`SA1`'s branch field is `A1_FILIAL`, confirmed via `ERROR: column "sa1_filial" does not exist` when the naive guess was tried).
  - `GqlQueryBuilder():new(oConfig as object) as object`
  - `GqlQueryBuilder():build(cTable as character, cFilialField as character, aScalarFields as array, oArgs as json, cOrderKey as character, cExtraWhere as character) as character` — returns the full SQL text ready to run via `TCQuery`; `cFilialField` is the real branch column name (see `getFilialField` above); `cExtraWhere` lets the executor inject an already-escaped parent-key join condition for nested relationship queries (Task 9) without the query builder needing to know about relationships itself.
  - `GqlQueryBuilder():EscapeValue(cValue as character) as character` (static) — single-quote doubling; the only sanctioned way any value reaches SQL text built by this class. This environment's query execution (`TCQuery`, from `topconn.ch`) has no bind-parameter support, so escaping replaces bind arrays as the injection-prevention mechanism (verified against the real server — see Global Constraints).

**Symbols to validate before compiling:** `StrTran()`, `cValToChar()`, `cFilAnt` (Public var), `RetSqlName()` — SQL execution, escaping and branch-value approach already verified against the real running server, see the Global Constraints notes on SQL execution and on `xFilial()`/`cFilAnt`.

- [ ] **Step 1: Add `getOrderKey` and `getFilialField` to `core/dictionary-reader.tlpp`**

Add both declarations to the existing `class GqlDictionaryReader ... endclass` block:

```tlpp
    public method getOrderKey(cTable as character) as character
    public method getFilialField(cTable as character) as character
```

Then add the implementations below the class's other implementations (after
`getRelations`'s `endmethod`, before `endnamespace`):

```tlpp
/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias
@return Character - comma-joined key field list from SIX order 1;
        falls back to the first scalar field of the table if no SIX
        row exists for order 1.
/@*/
method getOrderKey(cTable as character) as character class GqlDictionaryReader
    local cAlq   := GetNextAlias() as character
    local cSixTable := RetSqlName("SIX") as character
    local cQuery := "" as character
    local cKey   := "" as character
    local aFields as array

    if !empty(cSixTable)
        // ponytail: SIX not registered in every Protheus deployment (confirmed
        // empty RetSqlName against the live server this plan was verified
        // against) - fall straight through to the scalar-field fallback below
        // instead of running a malformed query.
        cQuery := "SELECT X6_CHAVE AS RKEY FROM " + cSixTable + ;
                   " WHERE D_E_L_E_T_ = ' ' AND X6_ARQUIVO = '" + cTable + "' AND X6_ORDEM = '1'"
        TCQuery cQuery New Alias &cAlq
        (cAlq)->(dbGoTop())
        if !(cAlq)->(Eof())
            cKey := alltrim((cAlq)->RKEY)
        endif
        (cAlq)->(dbCloseArea())
    endif

    if !empty(cKey)
        return cKey
    endif

    aFields := ::getTableFields(cTable)
    if len(aFields) > 0
        return aFields[1]["name"]
    endif
    return ""
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias, e.g. "SA1"
@return Character - the real branch field name for cTable (e.g. "A1_FILIAL"),
        found by suffix match against SX3, or "" if the table has none.
        Queries SX3 directly (not via getTableFields()) since the branch
        field is used internally for the mandatory filial filter and must
        be found even if X3_VISUAL = "N" or it matches a denyFields pattern.
/@*/
method getFilialField(cTable as character) as character class GqlDictionaryReader
    local cAlq    := GetNextAlias() as character
    local cQuery  := "SELECT X3_CAMPO AS FCAMPO FROM " + RetSqlName("SX3") + ;
                      " WHERE D_E_L_E_T_ = ' ' AND X3_ARQUIVO = '" + cTable + "'" as character
    local cField  := "" as character
    local cResult := "" as character

    TCQuery cQuery New Alias &cAlq
    (cAlq)->(dbGoTop())
    while !(cAlq)->(Eof())
        cField := alltrim((cAlq)->FCAMPO)
        if right(cField, 7) == "_FILIAL"
            cResult := cField
        endif
        (cAlq)->(dbSkip())
    enddo
    (cAlq)->(dbCloseArea())

    return cResult
endmethod
```

- [ ] **Step 2: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/dictionary-reader.tlpp`
Expected: compile succeeds.

- [ ] **Step 3: Write `core/query-builder.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlQueryBuilder - turns a table name, a scalar field list and parsed
      GraphQL arguments into a paginated SQL query string. Every query
      unconditionally gets the filial and D_E_L_E_T_ = ' ' filters — the
      caller cannot override or omit them (this environment runs on
      PostgreSQL, whose MVCC needs no lock hint on reads, so %nolock% is
      not used here — see Global Constraints). This environment's query
      execution path (`TCQuery ... New Alias &cAlias`, from `topconn.ch`)
      has no bind-parameter support, so every value that reaches the SQL
      text goes through EscapeValue() (single-quote doubling) first —
      never raw string concatenation of client-supplied values.
      ponytail: pagination uses ROW_NUMBER() OVER (ORDER BY <SIX order 1>)
      wrapped in a subquery — portable across the SQL Server/Oracle/
      PostgreSQL backends Protheus targets. Add cursor pagination if
      offset-based paging on huge tables becomes a measured bottleneck.
/@*/
class GqlQueryBuilder
    private data oConfig as object

    public method new(oConfig as object) as object
    public method build(cTable as character, cFilialField as character, aScalarFields as array, oArgs as json, cOrderKey as character, cExtraWhere as character) as character
    method resolveLimit(oArgs as json) as numeric
    method resolveOffset(oArgs as json) as numeric
    method applyFilters(oArgs as json) as character
    method opToSql(cOp as character) as character
    method joinFields(aFields as array) as character
    static method EscapeValue(cValue as character) as character
endclass

method new(oConfig as object) as object class GqlQueryBuilder
    ::oConfig := oConfig
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cTable Character - table alias
@param cFilialField Character - the real branch field name for cTable
       (e.g. "A1_FILIAL" for "SA1"; see GqlDictionaryReader:getFilialField()
       — never the same as cTable + "_FILIAL", the field prefix and the
       table alias are not the same string)
@param aScalarFields Array - field names to select
@param oArgs JSON - parsed GraphQL arguments (limit, offset, filter)
@param cOrderKey Character - comma-joined ORDER BY field list
@param cExtraWhere Character - additional, already-safe WHERE fragment, or
       "" (used by the executor to scope nested relationship queries to
       the parent row's key; the executor is responsible for escaping any
       value it interpolates there via EscapeValue())
@return Character - the full, ready-to-run SQL text
/@*/
method build(cTable as character, cFilialField as character, aScalarFields as array, oArgs as json, cOrderKey as character, cExtraWhere as character) as character class GqlQueryBuilder
        local nLimit   := ::resolveLimit(oArgs) as numeric
        local nOffset  := ::resolveOffset(oArgs) as numeric
        local cFilialEsc := GqlQueryBuilder():EscapeValue(cFilAnt) as character
        local cWhere   := "D_E_L_E_T_ = ' '" as character
        local cSelect  := ::joinFields(aScalarFields) as character
        local cFilterWhere as character
        local cSql     as character

        if !empty(cFilialField)
            cWhere += " AND " + cFilialField + " = '" + cFilialEsc + "'"
        endif

        cFilterWhere := ::applyFilters(oArgs)
        if !empty(cFilterWhere)
            cWhere += " AND " + cFilterWhere
        endif

        if !empty(cExtraWhere)
            cWhere += " AND " + cExtraWhere
        endif

        cSql := "SELECT " + cSelect + " FROM (" + ;
                 "SELECT " + cSelect + ", ROW_NUMBER() OVER (ORDER BY " + cOrderKey + ") AS GQL_RN" + ;
                 " FROM " + RetSqlName(cTable) + " WHERE " + cWhere + ;
                 ") GQL_PAGE WHERE GQL_RN > " + cValToChar(nOffset) + " AND GQL_RN <= " + cValToChar(nOffset + nLimit)

        return cSql
    endmethod

    method resolveLimit(oArgs as json) as numeric class GqlQueryBuilder
        local nLimit := ::oConfig:getDefaultPageSize() as numeric
        if oArgs["limit"] != nil
            nLimit := oArgs["limit"]["value"]
        endif
        if nLimit > ::oConfig:getMaxPageSize()
            nLimit := ::oConfig:getMaxPageSize()
        endif
        return nLimit
    endmethod

    method resolveOffset(oArgs as json) as numeric class GqlQueryBuilder
        if oArgs["offset"] != nil
            return oArgs["offset"]["value"]
        endif
        return 0
    endmethod

    method applyFilters(oArgs as json) as character class GqlQueryBuilder
        local oFilterArg := oArgs["filter"] as json
        local aFilters := {} as array
        local aClauses := {} as array
        local nI       := 0 as numeric
        local oFilter  as json
        local cOp      as character
        local cSqlOp   as character
        local cResult  := "" as character

        if oFilterArg == nil
            return ""
        endif
        aFilters := oFilterArg["value"]

        for nI := 1 to len(aFilters)
            oFilter := aFilters[nI]["value"]
            cOp     := oFilter["op"]["value"]
            cSqlOp  := ::opToSql(cOp)
            aAdd(aClauses, oFilter["field"]["value"] + " " + cSqlOp + " '" + GqlQueryBuilder():EscapeValue(oFilter["value"]["value"]) + "'")
        next nI

        for nI := 1 to len(aClauses)
            if nI > 1
                cResult += " AND "
            endif
            cResult += aClauses[nI]
        next nI

        return cResult
    endmethod

    method opToSql(cOp as character) as character class GqlQueryBuilder
        if cOp == "eq"
            return "="
        elseif cOp == "gt"
            return ">"
        elseif cOp == "gte"
            return ">="
        elseif cOp == "lt"
            return "<"
        elseif cOp == "lte"
            return "<="
        endif
        return "=" // GqlValidator already rejects unsupported operators before build() runs
    endmethod

    method joinFields(aFields as array) as character class GqlQueryBuilder
        local cResult := "" as character
        local nI      := 0 as numeric
        for nI := 1 to len(aFields)
            if nI > 1
                cResult += ", "
            endif
            cResult += aFields[nI]
        next nI
        return cResult
    endmethod

    /*/{Protheus.doc}
    @type Static Function
    @author GraphQL Engine Team
    @since 3.0.0
    @param cValue Character - raw value to interpolate into a SQL string literal
    @return Character - cValue with every single quote doubled, safe to wrap
            in '...' in SQL text built by this class
    /@*/
    method EscapeValue(cValue as character) as character class GqlQueryBuilder
        return StrTran(cValue, "'", "''")
    endmethod

endnamespace
```

- [ ] **Step 4: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/query-builder.tlpp`
Expected: compile succeeds.

- [ ] **Step 5: Commit**

```bash
git add custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp
git commit -m "feat(graphql): add bound, paginated SQL query builder

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Executor — full query execution, nested relationships, entry point wiring

**Files:**
- Create: `custom/backoffice/graphql/core/executor.tlpp`
- Modify: `custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp` (replace the `query` placeholder branch with real execution)
- Test: `tests/tir/test_graphql_pagination.tir`
- Test: `tests/tir/test_graphql_filter.tir`
- Test: `tests/tir/test_graphql_relationship.tir`
- Modify: `tests/tir/test_graphql_denylist.tir` (add field-level denial via a real query)

**Interfaces:**
- Consumes: `GqlParser` (Task 6), `GqlValidator` (Task 7), `GqlQueryBuilder` (Task 8), `GqlSchemaProvider`/`GqlDictionaryReader` (Task 3/4), `GqlErrors` (Task 3).
- Produces:
  - `GqlExecutor():new(oSchemaProvider as object, oDictionaryReader as object, oQueryBuilder as object) as object`
  - `GqlExecutor():execute(cQuerySource as character) as json` — returns `{"data": {...}}` or `{"errors": [...]}`

**Symbols to validate before compiling:** `TCQuery`/row iteration (same shape as Task 8's — validate once, reuse), `GqlDictionaryReader:getFilialField()`.

- [ ] **Step 1: Write the TIR tests first (they will fail — real query execution isn't wired yet)**

`tests/tir/test_graphql_pagination.tir`:
```python
"""
TIR Test — GraphQL query pagination (limit/offset, maxPageSize cap)
"""
from contrib.tir import Webapp
import json
import urllib.parse


class TestGraphQLPagination:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_respects_limit(self):
        gql = "{ SA1(limit: 3, offset: 0) { A1_COD A1_NOME } }"
        result = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql))
        data = json.loads(result.text)
        assert "data" in data
        rows = data["data"]["SA1"]
        assert isinstance(rows, list)
        assert len(rows) <= 3

    def test_offset_shifts_page(self):
        gql_page1 = "{ SA1(limit: 2, offset: 0) { A1_COD } }"
        gql_page2 = "{ SA1(limit: 2, offset: 2) { A1_COD } }"
        r1 = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql_page1))
        r2 = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql_page2))
        rows1 = json.loads(r1.text)["data"]["SA1"]
        rows2 = json.loads(r2.text)["data"]["SA1"]
        codes1 = {r["A1_COD"] for r in rows1}
        codes2 = {r["A1_COD"] for r in rows2}
        assert codes1.isdisjoint(codes2)
```

`tests/tir/test_graphql_filter.tir`:
```python
"""
TIR Test — GraphQL query filtering
"""
from contrib.tir import Webapp
import json
import urllib.parse


class TestGraphQLFilter:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_filter_eq_narrows_results(self):
        gql = '{ SA1(limit: 10, filter: [{field: "A1_COD", op: "eq", value: "000001"}]) { A1_COD } }'
        result = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql))
        data = json.loads(result.text)
        rows = data["data"]["SA1"]
        assert all(r["A1_COD"].strip() == "000001" for r in rows)

    def test_filter_injection_value_is_harmless(self):
        gql = "{ SA1(limit: 5, filter: [{field: \"A1_COD\", op: \"eq\", value: \"' OR '1'='1\"}]) { A1_COD } }"
        result = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql))
        assert result.status_code == 200
        data = json.loads(result.text)
        assert "data" in data
        assert data["data"]["SA1"] == []
```

`tests/tir/test_graphql_relationship.tir`:
```python
"""
TIR Test — nested relationship resolution via SX9
"""
from contrib.tir import Webapp
import json
import urllib.parse


class TestGraphQLRelationship:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_nested_relation_resolves(self):
        # NOTE: replace SC5 with a table this environment's SX9 actually
        # links from SA1 before running (confirm via execute-sql first).
        gql = "{ SA1(limit: 1) { A1_COD SC5 { C5_NUM } } }"
        result = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql))
        data = json.loads(result.text)
        assert "data" in data
        rows = data["data"]["SA1"]
        if rows:
            assert "SC5" in rows[0]
            assert isinstance(rows[0]["SC5"], list)
```

Append to `TestGraphQLDenylist` in `tests/tir/test_graphql_denylist.tir`:
```python
    def test_denied_field_rejected_in_real_query(self):
        gql = "{ SA1(limit: 1) { A1_COD A1_SENHA } }"
        result = self.client.http_get("/graphql?query=" + urllib.parse.quote_plus(gql))
        data = json.loads(result.text)
        assert "errors" in data
```

- [ ] **Step 2: Run the new/extended tests to confirm they fail (query param still returns the placeholder error)**

Run: `pytest tests/tir/test_graphql_pagination.tir tests/tir/test_graphql_filter.tir tests/tir/test_graphql_relationship.tir tests/tir/test_graphql_denylist.tir -v`
Expected: FAIL — every real query returns `{"errors":[{"message":"query execution not available yet"}]}` from Task 3's placeholder.

- [ ] **Step 3: Write `core/executor.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "topconn.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.0.0
@desc GqlExecutor - parses, validates and executes a GraphQL query source,
      resolving root table fields and SX9-driven nested relationships.
/@*/
class GqlExecutor
    private data oSchemaProvider    as object
    private data oDictionaryReader  as object
    private data oQueryBuilder      as object

    public method new(oSchemaProvider as object, oDictionaryReader as object, oQueryBuilder as object) as object
    public method execute(cQuerySource as character) as json
    method resolveTableField(oField as json, cExtraWhere as character) as array
    method resolveRelation(oParentType as json, cParentTable as character, oRelField as json, oParentRow as json) as array
    method isScalarField(oType as json, cName as character) as logical
    method fieldNames(aSelection as array) as array
    method fieldAlias(oField as json) as character
endclass

method new(oSchemaProvider as object, oDictionaryReader as object, oQueryBuilder as object) as object class GqlExecutor
    ::oSchemaProvider   := oSchemaProvider
    ::oDictionaryReader := oDictionaryReader
    ::oQueryBuilder     := oQueryBuilder
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.0.0
@param cQuerySource Character - raw GraphQL query text
@return JSON - {"data": {...}} on success, {"errors": [...]} on failure
/@*/
method execute(cQuerySource as character) as json class GqlExecutor
        local oParser    := GqlParser():new(cQuerySource) as object
        local oValidator := GqlValidator():new(::oSchemaProvider) as object
        local oDoc       as json
        local aValErrors as array
        local aDefs      as array
        local aSel       as array
        local oData      as json
        local nI         := 0 as numeric
        local nJ         := 0 as numeric
        local oResult    as json

        oDoc := oParser:parse()
        if oDoc == nil
            return GqlErrors():fromArray(oParser:getErrors())
        endif

        aValErrors := oValidator:validate(oDoc)
        if len(aValErrors) > 0
            return GqlErrors():fromArray(aValErrors)
        endif

        oData := JsonObject():New()
        aDefs := oDoc["definitions"]
        for nI := 1 to len(aDefs)
            aSel := aDefs[nI]["selectionSet"]
            for nJ := 1 to len(aSel)
                oData[aSel[nJ]["name"]] := ::resolveTableField(aSel[nJ], "")
            next nJ
        next nI

        oResult := JsonObject():New()
        oResult["data"] := oData
        return oResult
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 3.0.0
    @param oField JSON - Field AST node for a root or nested table field
    @param cExtraWhere Character - already-safe (escaped) parent-key WHERE
           fragment for nested calls, or ""
    @return Array - list of row objects (JSON), each with requested scalars
            and resolved nested relation lists
    /@*/
    method resolveTableField(oField as json, cExtraWhere as character) as array class GqlExecutor
        local cTable       := oField["name"] as character
        local oType        := ::oSchemaProvider:getType(cTable) as json
        local aScalarSel   := {} as array
        local aRelationSel := {} as array
        local nI           := 0 as numeric
        local oSel         as json
        local cOrderKey    as character
        local cFilialField as character
        local cSql         as character
        local aRows        := {} as array
        local cAlq         as character
        local oRow         as json
        local nJ           := 0 as numeric

        for nI := 1 to len(oField["selectionSet"])
            oSel := oField["selectionSet"][nI]
            if ::isScalarField(oType, oSel["name"])
                aAdd(aScalarSel, oSel)
            else
                aAdd(aRelationSel, oSel)
            endif
        next nI

        cOrderKey    := ::oDictionaryReader:getOrderKey(cTable)
        cFilialField := ::oDictionaryReader:getFilialField(cTable)
        cSql         := ::oQueryBuilder:build(cTable, cFilialField, ::fieldNames(aScalarSel), oField["arguments"], cOrderKey, cExtraWhere)

        cAlq := GetNextAlias()
        TCQuery cSql New Alias &cAlq
        (cAlq)->(dbGoTop())
        while !(cAlq)->(Eof())
            oRow := JsonObject():New()
            for nI := 1 to len(aScalarSel)
                oRow[::fieldAlias(aScalarSel[nI])] := (cAlq)->(FieldGet(FieldPos(aScalarSel[nI]["name"])))
            next nI
            for nJ := 1 to len(aRelationSel)
                oRow[aRelationSel[nJ]["name"]] := ::resolveRelation(oType, cTable, aRelationSel[nJ], oRow)
            next nJ
            aAdd(aRows, oRow)
            (cAlq)->(dbSkip())
        enddo
        (cAlq)->(dbCloseArea())

        return aRows
    endmethod

    method resolveRelation(oParentType as json, cParentTable as character, oRelField as json, oParentRow as json) as array class GqlExecutor
        local aRelations := ::oDictionaryReader:getRelations(cParentTable) as array
        local nI         := 0 as numeric
        local oRelMeta    as json
        local cLocalField  as character
        local cForeignField as character
        local cLocalValue as character

        for nI := 1 to len(aRelations)
            if aRelations[nI]["relatedTable"] == oRelField["name"]
                oRelMeta := aRelations[nI]
                exit
            endif
        next nI

        if oRelMeta == nil
            return {}
        endif

        cLocalField    := oRelMeta["localFields"]
        cForeignField  := oRelMeta["foreignFields"]
        cLocalValue    := GqlQueryBuilder():EscapeValue(cValToChar(oParentRow[cLocalField]))

        return ::resolveTableField(oRelField, cForeignField + " = '" + cLocalValue + "'")
    endmethod

    method isScalarField(oType as json, cName as character) as logical class GqlExecutor
        local aFields := oType["fields"] as array
        local nI      := 0 as numeric
        for nI := 1 to len(aFields)
            if aFields[nI]["name"] == cName
                return .T.
            endif
        next nI
        return .F.
    endmethod

    method fieldNames(aSelection as array) as array class GqlExecutor
        local aResult := {} as array
        local nI      := 0 as numeric
        for nI := 1 to len(aSelection)
            aAdd(aResult, aSelection[nI]["name"])
        next nI
        return aResult
    endmethod

    method fieldAlias(oField as json) as character class GqlExecutor
        if oField["alias"] != nil
            return oField["alias"]
        endif
        return oField["name"]
    endmethod

endnamespace
```

Note: `resolveRelation`'s join uses only the first field of `localFields`/`foreignFields` (assumes single-field SX9 keys). If this environment's SX9 rules use composite keys (comma-separated `X9_EXPDOM`), extend `cLocalField`/`cForeignField` handling to loop over the split field list before this task is considered done — confirm single- vs composite-key usage via `execute-sql` on SX9 first.

- [ ] **Step 4: Compile to verify no syntax errors**

Run: `compile.sh custom/backoffice/graphql/core/executor.tlpp`
Expected: compile succeeds.

- [ ] **Step 5: Wire the executor into the entry point**

In `entrypoints/service.entrypoint.tlpp`, no include is needed for
`GqlExecutor` — see the Global Constraints note on cross-file `#include`.

This project's `Local`/`Private` declarations must all sit at the top of
the function, before any executable statement (never mid-flow, per this
project's TLPP conventions — a `local` inside an `if` block is a compile
error, C2051 "LOCAL declaration follows executable statement"). Add
`oExecutor` to the existing top-of-function `local` block:
```tlpp
    local oExecutor  as object
```
(alongside `oConfig`, `oAccess`, `oDict`, `oSchema`, `jParams`, `cQuery`, `cTypeName`, `oResult`).

Then replace:
```tlpp
    if !empty(cQuery)
        // Wired in Task 9 (full parse/validate/execute pipeline).
        oResult := custom.backoffice.graphql.GqlErrors():single("query execution not available yet")
```
with:
```tlpp
    if !empty(cQuery)
        oExecutor := custom.backoffice.graphql.GqlExecutor():new(oSchema, oDict, custom.backoffice.graphql.GqlQueryBuilder():new(oConfig))
        oResult := oExecutor:execute(cQuery)
```

- [ ] **Step 6: Compile and deploy**

```bash
compile.sh custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
deploy-rpo.sh
```
Expected: compiles succeed, RPO deployed.

- [ ] **Step 7: Run all GraphQL TIR tests**

Run: `pytest tests/tir/test_graphql_introspection.tir tests/tir/test_graphql_dynamic_type.tir tests/tir/test_graphql_denylist.tir tests/tir/test_graphql_pagination.tir tests/tir/test_graphql_filter.tir tests/tir/test_graphql_relationship.tir -v`
Expected: all pass. If `test_graphql_relationship.tir` fails because `SA1`→`SC5` isn't a real SX9 rule in this environment, replace the table names in that test with a confirmed real pair before re-running (see the note left in Step 1).

- [ ] **Step 8: Commit**

```bash
git add custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp tests/tir/test_graphql_pagination.tir tests/tir/test_graphql_filter.tir tests/tir/test_graphql_relationship.tir tests/tir/test_graphql_denylist.tir
git commit -m "feat(graphql): execute real queries with pagination, filters and nested SX9 relations

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Documentation and final full-suite verification

**Files:**
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/configuration.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Write `README.md`**

```markdown
# GraphQL Core Engine (Protheus)

Dynamic GraphQL server over the Protheus data dictionary (SX2/SX3/SX9),
running as a TLPP AppServer REST entry point.

## Endpoint

- `GET /graphql` — schema type names (deny-list applied)
- `GET /graphql?type=<TABLE>` — full type detail for one table (fields + relations)
- `GET /graphql?query=<url-encoded GraphQL text>` — execute a query

## Example

```
{ SA1(limit: 5, filter: [{field: "A1_COD", op: "eq", value: "000001"}]) {
    A1_COD
    A1_NOME
    SC5 { C5_NUM }
} }
```

## Configuration

See `docs/configuration.md`. **`compile.sh`/`deploy-rpo.sh` only ever handle
compiled `.tlpp` sources** — `custom/backoffice/graphql/config/graphql-config.json`
must be copied to the AppServer's source path separately (same location as
the compiled sources — check `appserver.ini`'s `[P12] SourcePath=`). Without
it, the deny-list silently falls back to empty and every table becomes
visible — confirmed against a live server during development.

## Architecture

See `docs/architecture.md` and
`docs/superpowers/specs/2026-08-13-graphql-core-engine-design.md`.

## Tests

TIR (Python e2e) under `tests/tir/`. Run with `pytest tests/tir/ -v`
against a running Protheus AppServer with this RPO deployed.

## Sub-project roadmap

This is sub-project 1 of 6: Core Engine (this repo) → Mutations → Auth →
Field Hooks → SDK Generator → Console PO-UI. See the design spec for the
full roadmap and how each later sub-project plugs into this engine.
```

- [ ] **Step 2: Write `docs/architecture.md`**

```markdown
# Architecture

Request pipeline:

```
GET /graphql --> GQLSERVICE (entrypoints/service.entrypoint.tlpp)
             --> GqlLexer + GqlParser (core/lexer.tlpp, core/parser.tlpp)
             --> GqlValidator (core/validator.tlpp)
             --> GqlExecutor (core/executor.tlpp)
                 --> GqlQueryBuilder (core/query-builder.tlpp)
                 --> GqlDictionaryReader (core/dictionary-reader.tlpp)
             --> JSON response
```

Schema is never hand-written: `GqlSchemaProvider` (core/schema-provider.tlpp)
builds GraphQL types lazily from SX2 (tables) and SX3 (fields), and
relationship fields from SX9. Tables/fields are filtered by
`GqlAccessControl` (core/access-control.tlpp) against
`config/graphql-config.json`'s deny-lists before anything is cached.

The permission hook (`GqlAccessControl:allowField`) always returns `.T.`
in this sub-project — it exists so the Auth sub-project can wire in real
per-user permissions without touching any other file.
```

- [ ] **Step 3: Write `docs/configuration.md`**

```markdown
# Configuration

`custom/backoffice/graphql/config/graphql-config.json`:

| Key | Type | Meaning |
|---|---|---|
| `denyTables` | array of wildcard strings | Table aliases never exposed, e.g. `"SRH*"` |
| `denyFields` | array of wildcard strings | Field names never exposed, e.g. `"*SENHA*"` |
| `pagination.defaultPageSize` | number | `limit` used when the query omits it |
| `pagination.maxPageSize` | number | Hard cap on `limit`, even if the query asks for more |
| `schemaCacheTtlSeconds` | number | How long a table's generated type stays cached before automatic rebuild |

Wildcards support `*` as "any run of characters." Denied tables/fields
never appear in introspection or query results, regardless of query shape.
```

- [ ] **Step 4: Run the full TIR suite one more time as a final gate**

Run: `pytest tests/tir/ -v`
Expected: all tests pass (introspection, dynamic type, denylist, pagination, filter, relationship).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture.md docs/configuration.md
git commit -m "docs(graphql): add README, architecture and configuration docs for the core engine

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
