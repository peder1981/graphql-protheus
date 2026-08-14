# GraphQL Mutations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `createTABLE`/`updateTABLE`/`deleteTABLE` GraphQL mutations over the tables already exposed by the Core Engine, gated by a new per-table allow-list, validated against SX3 (required/type/length), writing via `TCSqlExec` with mandatory filial scoping and soft-delete, and returning the affected row through the existing query-execution path.

**Architecture:** A parallel write pipeline alongside the read pipeline: `GqlMutationSchema` (allow-list-gated type exposure) → `GqlInputValidator` (SX3-driven input checks) → `GqlMutationBuilder` (SQL text for INSERT/UPDATE) → `GqlMutationExecutor` (orchestrates parse → validate → pre-existence check → write → re-select via the existing `GqlExecutor`/`GqlQueryBuilder`). The REST entry point peeks the parsed document's operation type and dispatches to either the existing `GqlExecutor` (query) or the new `GqlMutationExecutor` (mutation) — no changes to `lexer.tlpp`, `parser.tlpp`, `validator.tlpp`, or `query-builder.tlpp`. `executor.tlpp` needs one minimal change: `resolveTableField()` gains a `public` modifier so `GqlMutationExecutor` can call it cross-class to re-select the affected row (see Global Constraints).

**Tech Stack:** TLPP (namespace `custom.backoffice.graphql`), Protheus AppServer REST (`@Get` annotation + implicit `oRest`), JSON (`JsonObject():New()`/`:FromJson()`/`:toJson()`/bracket access/`:GetNames()`), `TCSqlExec()`/`TCSQLError()` (`topconn.ch`) for writes, `TCQuery ... New Alias` for reads (unchanged from Core Engine), TIR/Python for e2e tests, `~/.shared/protheus/compile/scripts/{compile.sh,deploy-rpo.sh}` for build/deploy.

**Spec:** `docs/superpowers/specs/2026-08-14-graphql-mutations-design.md`

## Global Constraints

- Every write is scoped by the branch field forced to `cFilAnt` (never client-supplied — same Public-var pattern the Core Engine already uses for reads, since `xFilial()`/`FWxFilial()` return blank in this `@Get` REST context) and by `D_E_L_E_T_ = ' '` in update/delete WHERE clauses (spec: Fluxos de escrita).
- Delete is always soft (`UPDATE ... SET D_E_L_E_T_ = '*' ...`), never a real SQL `DELETE` (spec: Não-objetivos).
- A table is writable only if it is BOTH in the new `allowMutations` config list AND passes the existing read deny-list (`denyTables`) — a table denied for reads can never become a mutation target even if mistakenly allow-listed (spec: Restrição de acesso). `allowMutations` takes exact table aliases, no wildcard (spec: Configuração) — unlike `denyTables`/`denyFields`, which do support `*`.
- A field the read path already excludes (`denyFields` match or `X3_VISUAL == "N"`) never appears in mutation input validation or SQL — `GqlInputValidator`/`GqlMutationBuilder` only ever iterate `GqlDictionaryReader:getTableFields(cTable)`'s result, never a client-supplied field list directly (spec: Restrição de acesso).
- No SX5 auto-numbering, no `FWFormModel`/MVC, no hard delete, no batch/multi-row mutations — all explicitly out of scope (spec: Não-objetivos). Do not add any of these speculatively.
- **Write mechanism — verified empirically against the live server** (containers `protheus`/`dbaccess`/`postgresql`/`license-server`) during planning, because the Core Engine's own `TCQuery ... New Alias &cAlias` (used for every read) is confirmed **unusable for writes**:
  - `TCQuery "UPDATE ..." New Alias &cAlq` on a non-`SELECT` statement crashes the request to an uncatchable HTTP 500 with **empty** `detailedMessage` — confirmed twice, from a clean compile/deploy, with and without `begin sequence/recover using` wrapped around it. This is not a normal AdvPL runtime error object (the `recover` block never runs) — treat it as a hard crash, not a catchable exception. **Never use `TCQuery ... New Alias` for anything but `SELECT`.**
  - `TCSqlExec(cStatement)` (`topconn.ch`, already included by every file that also uses `TCQuery`) is the correct write primitive — confirmed working end-to-end against the live PostgreSQL backend: returns a `numeric` status, `>= 0` on success (confirmed `0` for a real `UPDATE`), `< 0` on failure (confirmed `-19` for a deliberately malformed statement) — on failure, call `TCSQLError()` (no arguments) for the human-readable driver message, which is safe to log but must never be echoed verbatim to the GraphQL client (it includes internal thread/connection diagnostics). A malformed statement does **not** crash the request — `TCSqlExec` returns cleanly with a negative status, unlike `TCQuery`.
  - **There is no affected-row-count function in this build.** A function named `TCSQLRows()` does not exist — confirmed by the same uncatchable-crash signature as calling a made-up function name (`ZZZNONEXISTENTFUNC()`); an **unresolved function call in this REST context is always an uncatchable crash, never a normal runtime error**, regardless of whether the missing symbol is TC-prefixed or not. Because of this, update/delete existence checks in this plan use a **pre-write `SELECT` by key** (via the existing `GqlExecutor`/`GqlQueryBuilder`, scoped by an `cExtraWhere` key filter — the same mechanism the Core Engine already uses for nested relationship resolution) instead of inspecting rows-affected after the `UPDATE`. Do not call `TCSQLRows()`, or any other undocumented function, without confirming it exists the same way this constraint was confirmed — an unresolved symbol will crash the whole request, not just fail gracefully.
  - Every value interpolated into SQL text built by `GqlMutationBuilder` MUST go through `GqlQueryBuilder():EscapeValue(cValToChar(...))` (existing static method, unchanged) — same rule as the Core Engine's query path, extended to writes.
- **A TLPP method with no `public`/`private` access modifier on its declaration is NOT callable from another class, even within the same namespace — confirmed empirically, and it fails the same way an undefined function does: an uncatchable HTTP 500 crash, not a compile error and not a catchable runtime error.** A scratch two-class probe confirmed this directly: `oOther:unmarkedMethod(...)` crashed the request; changing only the declaration to `public method markedMethod(...)` (implementation line unchanged, per the existing two-part class-syntax rule) made the identical cross-class call work. This matters here because `GqlExecutor:resolveTableField(oField as json, cExtraWhere as character) as array` — the method `GqlMutationExecutor:fetchByKey()` (Task 5) calls to re-select a row through the existing read path — is declared **without** a modifier in the Core Engine's `executor.tlpp`. Task 5 includes a step to add `public` to that one declaration line (implementation line and every other method's modifier stay untouched). Do not skip this step, and do not assume any other unmarked method elsewhere in this codebase is safely cross-class-callable without the same kind of empirical check — self-calls via `::` from inside the declaring class (which is all the Core Engine's own code does) are unaffected either way.
- **Compiling a scratch/probe `.tlpp` file from outside this project's own directory produces an isolated `custom.rpo` that, once deployed, silently overwrites and wipes every previously-deployed class from this project** — confirmed during planning (an isolated-directory compile of a throwaway probe file, once deployed, made `/rest/graphql` 404 until the full Core Engine source set was recompiled from inside this project's own directory and redeployed). Any exploratory compile during implementation MUST run `compile.sh` from this project's root directory (`/home/peder/Projetos/GraphQL`), passing every source file that needs to remain in the RPO — never a throwaway directory. When probing an unconfirmed API/symbol, always restore the server to a clean, fully-recompiled state afterward before treating a task as done.
- **Symbol validation**: every new native/framework symbol below (`TCSqlExec`, `TCSQLError`, `JsonObject():GetNames()`) was confirmed against either the live server or `~/tdn-advpl-mirror` (a full local TDN AdvPL mirror) during planning — do not introduce a new unconfirmed symbol without the same empirical check; an unresolved symbol crashes the whole request uncatchably (see above), so "it looks plausible" is not sufficient here.
- **TLPP class syntax, `Local`/`Private` placement, `IIF()` ban, JSON API, `@Get` REST pattern, `TCQuery ... New Alias` for reads, encoding (CP-1252 `.tlpp` / UTF-8 `.json`)** — all identical to the Core Engine plan's Global Constraints (`docs/superpowers/plans/2026-08-13-graphql-core-engine.md`); every rule there still applies verbatim to every file in this plan and is not repeated in full here. In particular: two-part class declare/implement, no cross-file `#include` of this project's own `.tlpp` files, `Local`/`Private` only at the top of a method, `oRest` never explicitly declared, `:GetJsonText()`'s `"null"`-string quirk on missing keys.
- **Test strategy**: same as the Core Engine — no AdvPL/TLPP unit-test runner exists in this repo; `compile.sh` (zero errors) is the fast per-task signal, TIR (`pytest`, written but not locally runnable in this sandbox) is the runtime signal, verified instead via live `curl` against the running stack during implementation.

---

### Task 1: Config — `allowMutations` list

**Files:**
- Modify: `custom/backoffice/graphql/config/graphql-config.json`
- Modify: `custom/backoffice/graphql/core/config.tlpp:13-28` (class declaration), `custom/backoffice/graphql/core/config.tlpp:30-77` (`new()`), append a new method

**Interfaces:**
- Produces: `GqlConfig:getAllowMutations() as array` — returns the exact list of table aliases from `allowMutations` in `graphql-config.json`, `{}` if absent/missing file (same graceful-fallback pattern `getDenyTables()` already uses).

- [ ] **Step 1: Add `allowMutations` to the config JSON**

Edit `custom/backoffice/graphql/config/graphql-config.json` to:

```json
{
  "denyTables": ["SRH*", "SRA", "SR5"],
  "denyFields": ["*SENHA*", "*_PASSWORD*"],
  "allowMutations": ["SA1"],
  "pagination": { "defaultPageSize": 20, "maxPageSize": 200 },
  "schemaCacheTtlSeconds": 3600
}
```

(`SA1` is allow-listed here so Task 8's live TIR-equivalent `curl` verification and the TIR tests in Task 9 have a real writable table to exercise — `SA1` is the same table the Core Engine's own README example already queries.)

- [ ] **Step 2: Add the field, accessor, and JSON read in `config.tlpp`**

In the class declaration block (`custom/backoffice/graphql/core/config.tlpp`), add a new private field and public method:

```tlpp
class GqlConfig
    private data aDenyTables         as array
    private data aDenyFields         as array
    private data aAllowMutations     as array
    private data nDefaultPageSize    as numeric
    private data nMaxPageSize        as numeric
    private data nSchemaCacheTtlSecs as numeric

    public method new() as object
    public method getDenyTables() as array
    public method getDenyFields() as array
    public method getAllowMutations() as array
    public method getDefaultPageSize() as numeric
    public method getMaxPageSize() as numeric
    public method getSchemaCacheTtlSeconds() as numeric
    static method MatchWildcard(cPattern as character, cValue as character) as logical
    static method SplitOnStar(cPattern as character) as array
endclass
```

In `method new() as object class GqlConfig`, add the default initialization next to the existing ones:

```tlpp
    ::aDenyTables         := {}
    ::aDenyFields         := {}
    ::aAllowMutations     := {}
    ::nDefaultPageSize    := 20
    ::nMaxPageSize        := 200
    ::nSchemaCacheTtlSecs := 3600
```

And, alongside the existing `if oJson["denyTables"] != nil ... endif` / `if oJson["denyFields"] != nil ... endif` block, add:

```tlpp
    if oJson["allowMutations"] != nil
        ::aAllowMutations := oJson["allowMutations"]
    endif
```

Then add the new accessor method after `getDenyFields()`:

```tlpp
method getAllowMutations() as array class GqlConfig
    return ::aAllowMutations
endmethod
```

- [ ] **Step 3: Compile**

Run (from the project root):
```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp
```
Expected: `Compilation Results .: Total sources(1) Success(1) Errors(0)`.

- [ ] **Step 4: Deploy and verify live**

```bash
~/.shared/protheus/compile/scripts/deploy-rpo.sh .
```
Also copy the updated config JSON to the AppServer's `RootPath` (same deployment step the Core Engine's README documents as required and separate from the RPO):
```bash
docker cp custom/backoffice/graphql/config/graphql-config.json protheus:/protheus12/protheus_data/custom/backoffice/graphql/config/graphql-config.json
```
Then confirm the deny-list behavior is unaffected (regression check — `SRA` must still be absent):
```bash
curl -s "http://localhost:9995/rest/graphql" | grep -o '"SRA"'
```
Expected: no output (SRA still denied; config parsing of the new key didn't break existing parsing).

- [ ] **Step 5: Commit**

```bash
git add custom/backoffice/graphql/config/graphql-config.json custom/backoffice/graphql/core/config.tlpp
git commit -m "feat(graphql): add allowMutations config list"
```

---

### Task 2: `GqlInputValidator` — SX3-driven input validation

**Files:**
- Create: `custom/backoffice/graphql/core/input-validator.tlpp`

**Interfaces:**
- Consumes: `GqlDictionaryReader:getTableFields(cTable as character) as array` (existing — returns `{name, sx3Type, graphqlType}` per allowed/visible field), `GqlDictionaryReader:getOrderKey(cTable as character) as character` (existing — comma-joined key field list).
- Produces: `GqlInputValidator():new(oDictionaryReader as object) as object`, `GqlInputValidator:validateCreate(cTable as character, oInput as json) as array` (error message array, empty if valid), `GqlInputValidator:validateUpdate(cTable as character, oInput as json) as array`. Both consumed by `GqlMutationExecutor` in Task 4.

This class needs the SX3 field metadata (`sx3Type`, and — new for this task — length and required-ness) but `getTableFields()` only returns `{name, sx3Type, graphqlType}`, not `X3_TAMANHO`/`X3_OBRIGAT`. Rather than re-querying SX3 a second time from a new file (duplicating `dictionary-reader.tlpp`'s query), this task extends `GqlDictionaryReader:getTableFields()` itself to include the two extra columns — every existing caller (`GqlSchemaProvider:getType()`, `GqlExecutor`) already treats each field as a JSON object and only reads the keys it needs, so adding two more keys is additive and cannot break them.

- [ ] **Step 1: Extend `getTableFields()` to include length and required-ness**

Modify `custom/backoffice/graphql/core/dictionary-reader.tlpp`'s `getTableFields()` method (currently lines 70-99). Change the SQL and row-building to also read `X3_TAMANHO` and `X3_OBRIGAT`:

```tlpp
method getTableFields(cTable as character) as array class GqlDictionaryReader
    local aResult  := {} as array
    local cAlq     := GetNextAlias() as character
    local cQuery   := "SELECT X3_CAMPO AS FCAMPO, X3_TIPO AS FTIPO, X3_DECIMAL AS FDECIMAL, X3_VISUAL AS FVISUAL, X3_TAMANHO AS FTAM, X3_OBRIGAT AS FOBRIG" + ;
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
            oRow["maxLength"] := (cAlq)->FTAM
            oRow["required"] := alltrim((cAlq)->FOBRIG) == "S"
            aAdd(aResult, oRow)
        endif
        (cAlq)->(dbSkip())
    enddo
    (cAlq)->(dbCloseArea())

    return aResult
endmethod
```

- [ ] **Step 2: Compile the extended dictionary-reader**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp
```
Expected: 3/3 success.

- [ ] **Step 3: Verify live that reads still work unchanged**

```bash
~/.shared/protheus/compile/scripts/deploy-rpo.sh .
curl -s "http://localhost:9995/rest/graphql?type=SA1" | python3 -m json.tool | head -20
```
Expected: `A1_COD`/`A1_NOME`/etc. still listed under `fields`, same as before — the two new JSON keys on each field object don't break `GqlSchemaProvider:getType()`'s existing pass-through of the whole array.

- [ ] **Step 4: Write `input-validator.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.1.0
@desc GqlInputValidator - validates a mutation's input object against SX3
      metadata (required/type/length) before any write happens.
/@*/
class GqlInputValidator
    private data oDictionaryReader as object

    public method new(oDictionaryReader as object) as object
    public method validateCreate(cTable as character, oInput as json) as array
    public method validateUpdate(cTable as character, oInput as json) as array
    method validateField(oFieldMeta as json, uValue as variant, aErrors as array) as object
endclass

method new(oDictionaryReader as object) as object class GqlInputValidator
    ::oDictionaryReader := oDictionaryReader
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@param oInput JSON - parsed mutation input object (flat field map)
@return Array - error messages, empty if valid. Every field returned by
        GqlDictionaryReader:getTableFields() is checked: required fields
        must be present, and any present field's type/length is validated.
/@*/
method validateCreate(cTable as character, oInput as json) as array class GqlInputValidator
    local aFields := ::oDictionaryReader:getTableFields(cTable) as array
    local aErrors := {} as array
    local nI      := 0 as numeric
    local uValue  as variant

    for nI := 1 to len(aFields)
        uValue := oInput[aFields[nI]["name"]]
        if uValue == nil
            if aFields[nI]["required"]
                aAdd(aErrors, "Field '" + aFields[nI]["name"] + "' is required")
            endif
            loop
        endif
        ::validateField(aFields[nI], uValue, aErrors)
    next nI

    return aErrors
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@param oInput JSON - parsed mutation input object (flat field map)
@return Array - error messages, empty if valid. Update is partial: only
        fields actually present in oInput are validated (type/length);
        required-ness is not enforced here (an omitted field is simply not
        touched by the write) and key fields are validated by the caller
        separately (GqlMutationExecutor, via GqlDictionaryReader:getOrderKey()).
/@*/
method validateUpdate(cTable as character, oInput as json) as array class GqlInputValidator
    local aFields := ::oDictionaryReader:getTableFields(cTable) as array
    local aErrors := {} as array
    local nI      := 0 as numeric
    local uValue  as variant

    for nI := 1 to len(aFields)
        uValue := oInput[aFields[nI]["name"]]
        if uValue == nil
            loop
        endif
        ::validateField(aFields[nI], uValue, aErrors)
    next nI

    return aErrors
endmethod

method validateField(oFieldMeta as json, uValue as variant, aErrors as array) as object class GqlInputValidator
    local cType   := oFieldMeta["sx3Type"] as character
    local cName   := oFieldMeta["name"] as character
    local nMaxLen := oFieldMeta["maxLength"] as numeric

    if cType == "N"
        if valtype(uValue) != "N"
            aAdd(aErrors, "Field '" + cName + "' must be numeric")
        endif
    elseif cType == "L"
        if valtype(uValue) != "L"
            aAdd(aErrors, "Field '" + cName + "' must be boolean")
        endif
    elseif cType == "C"
        if valtype(uValue) != "C"
            aAdd(aErrors, "Field '" + cName + "' must be a string")
        elseif len(uValue) > nMaxLen
            aAdd(aErrors, "Field '" + cName + "' exceeds max length " + cValToChar(nMaxLen))
        endif
    endif

    return self
endmethod

endnamespace
```

- [ ] **Step 5: Compile**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/input-validator.tlpp
```
Expected: `Compilation Results .: Total sources(1) Success(1) Errors(0)`.

- [ ] **Step 6: Commit**

```bash
git add custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/input-validator.tlpp
git commit -m "feat(graphql): add SX3-driven mutation input validator"
```

---

### Task 3: `GqlMutationSchema` — allow-list-gated mutation type exposure

**Files:**
- Create: `custom/backoffice/graphql/core/mutation-schema.tlpp`

**Interfaces:**
- Consumes: `GqlConfig:getAllowMutations() as array` (Task 1), `GqlSchemaProvider:getType(cTable as character) as json` (existing — returns `nil` if the table is denied/unknown, else `{name, fields, relations}`).
- Produces: `GqlMutationSchema():new(oSchemaProvider as object, oConfig as object) as object`, `GqlMutationSchema:isMutable(cTable as character) as logical` (used by `GqlMutationExecutor` in Task 4 to gate every create/update/delete), `GqlMutationSchema:getMutationType(cTable as character) as json` (same shape as `GqlSchemaProvider:getType()`, `nil` if not mutable — consumed by future sub-projects per the spec's "Dependências", not by this plan's executor, which uses `isMutable()` + the dictionary reader directly).

- [ ] **Step 1: Write `mutation-schema.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.1.0
@desc GqlMutationSchema - a table is a valid mutation target only if it is
      BOTH in the allowMutations config list AND passes the read-path
      deny-list (GqlSchemaProvider:getType() already returns nil for a
      denied/unknown table) - never a mutation-only bypass of the deny-list.
/@*/
class GqlMutationSchema
    private data oSchemaProvider as object
    private data oConfig         as object

    public method new(oSchemaProvider as object, oConfig as object) as object
    public method isMutable(cTable as character) as logical
    public method getMutationType(cTable as character) as json
endclass

method new(oSchemaProvider as object, oConfig as object) as object class GqlMutationSchema
    ::oSchemaProvider := oSchemaProvider
    ::oConfig         := oConfig
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@return Logical - .T. only if cTable is in allowMutations AND the read
        deny-list does not block it (GqlSchemaProvider:getType() != nil)
/@*/
method isMutable(cTable as character) as logical class GqlMutationSchema
    local aAllow := ::oConfig:getAllowMutations() as array

    if ascan(aAllow, {|c| c == cTable}) == 0
        return .F.
    endif

    return ::oSchemaProvider:getType(cTable) != nil
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@return JSON - same {name, fields, relations} shape as
        GqlSchemaProvider:getType(), or nil if cTable is not mutable
/@*/
method getMutationType(cTable as character) as json class GqlMutationSchema
    if !::isMutable(cTable)
        return nil
    endif
    return ::oSchemaProvider:getType(cTable)
endmethod

endnamespace
```

- [ ] **Step 2: Compile**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/mutation-schema.tlpp
```
Expected: `Compilation Results .: Total sources(1) Success(1) Errors(0)`.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/mutation-schema.tlpp
git commit -m "feat(graphql): add mutation allow-list schema gate"
```

---

### Task 4: `GqlMutationBuilder` — SQL text for create/update/soft-delete

**Files:**
- Create: `custom/backoffice/graphql/core/mutation-builder.tlpp`

**Interfaces:**
- Consumes: `GqlQueryBuilder():EscapeValue(cValue as character) as character` (existing static method, unchanged).
- Produces: `GqlMutationBuilder():new() as object`, `GqlMutationBuilder:buildInsert(cTable as character, cFilialField as character, oInput as json, aFieldNames as array) as character`, `GqlMutationBuilder:buildUpdate(cTable as character, cFilialField as character, oInput as json, aKeyFields as array, aSetFields as array) as character`, `GqlMutationBuilder:buildSoftDelete(cTable as character, cFilialField as character, oInput as json, aKeyFields as array) as character`. All consumed by `GqlMutationExecutor` in Task 5.

`aFieldNames`/`aKeyFields`/`aSetFields` are plain arrays of field-name strings (not the `{name, sx3Type, ...}` objects `getTableFields()` returns) — the caller (Task 5) is responsible for extracting names from whichever field-metadata list it already has, keeping this class free of any dictionary-reader dependency (pure SQL-text assembly, mirroring how `query-builder.tlpp` has no dictionary-reader dependency either).

- [ ] **Step 1: Write `mutation-builder.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.1.0
@desc GqlMutationBuilder - turns a table name, the real branch field name,
      a validated input object and a field-name list into ready-to-run SQL
      text for INSERT/UPDATE (soft-delete uses UPDATE too). The branch
      field is always forced to cFilAnt - never read from oInput - exactly
      like GqlQueryBuilder does for reads. Every value goes through
      GqlQueryBuilder():EscapeValue(cValToChar(...)) before reaching SQL
      text - never raw concatenation of client-supplied values.
/@*/
class GqlMutationBuilder
    public method new() as object
    public method buildInsert(cTable as character, cFilialField as character, oInput as json, aFieldNames as array) as character
    public method buildUpdate(cTable as character, cFilialField as character, oInput as json, aKeyFields as array, aSetFields as array) as character
    public method buildSoftDelete(cTable as character, cFilialField as character, oInput as json, aKeyFields as array) as character
    method escapedValue(uValue as variant) as character
    method keyWhere(oInput as json, aKeyFields as array) as character
endclass

method new() as object class GqlMutationBuilder
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@param cFilialField Character - real branch field name for cTable, or ""
       if the table has none
@param oInput JSON - validated create input
@param aFieldNames Array - field names to insert, from oInput's keys
       (the caller already filtered this to known/allowed fields)
@return Character - full INSERT statement text
/@*/
method buildInsert(cTable as character, cFilialField as character, oInput as json, aFieldNames as array) as character class GqlMutationBuilder
    local cCols   := "" as character
    local cVals   := "" as character
    local nI      := 0 as numeric

    for nI := 1 to len(aFieldNames)
        if nI > 1
            cCols += ", "
            cVals += ", "
        endif
        cCols += aFieldNames[nI]
        cVals += "'" + ::escapedValue(oInput[aFieldNames[nI]]) + "'"
    next nI

    if !empty(cFilialField)
        cCols += ", " + cFilialField
        cVals += ", '" + GqlQueryBuilder():EscapeValue(cFilAnt) + "'"
    endif

    return "INSERT INTO " + RetSqlName(cTable) + " (" + cCols + ") VALUES (" + cVals + ")"
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@param cFilialField Character - real branch field name, or ""
@param oInput JSON - validated update input (key fields + fields to change)
@param aKeyFields Array - field names identifying the row (WHERE)
@param aSetFields Array - field names to change (SET) - never includes any
       of aKeyFields
@return Character - full UPDATE statement text, scoped by key + filial +
        D_E_L_E_T_ = ' '
/@*/
method buildUpdate(cTable as character, cFilialField as character, oInput as json, aKeyFields as array, aSetFields as array) as character class GqlMutationBuilder
    local cSet := "" as character
    local nI   := 0 as numeric
    local cWhere := "D_E_L_E_T_ = ' '" as character

    for nI := 1 to len(aSetFields)
        if nI > 1
            cSet += ", "
        endif
        cSet += aSetFields[nI] + " = '" + ::escapedValue(oInput[aSetFields[nI]]) + "'"
    next nI

    cWhere += " AND " + ::keyWhere(oInput, aKeyFields)
    if !empty(cFilialField)
        cWhere += " AND " + cFilialField + " = '" + GqlQueryBuilder():EscapeValue(cFilAnt) + "'"
    endif

    return "UPDATE " + RetSqlName(cTable) + " SET " + cSet + " WHERE " + cWhere
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cTable Character - table alias
@param cFilialField Character - real branch field name, or ""
@param oInput JSON - delete input (key fields only)
@param aKeyFields Array - field names identifying the row (WHERE)
@return Character - UPDATE statement text setting D_E_L_E_T_ = '*',
        scoped by key + filial + D_E_L_E_T_ = ' ' (never touches an
        already-deleted row)
/@*/
method buildSoftDelete(cTable as character, cFilialField as character, oInput as json, aKeyFields as array) as character class GqlMutationBuilder
    local cWhere := "D_E_L_E_T_ = ' '" as character

    cWhere += " AND " + ::keyWhere(oInput, aKeyFields)
    if !empty(cFilialField)
        cWhere += " AND " + cFilialField + " = '" + GqlQueryBuilder():EscapeValue(cFilAnt) + "'"
    endif

    return "UPDATE " + RetSqlName(cTable) + " SET D_E_L_E_T_ = '*' WHERE " + cWhere
endmethod

method escapedValue(uValue as variant) as character class GqlMutationBuilder
    return GqlQueryBuilder():EscapeValue(cValToChar(uValue))
endmethod

method keyWhere(oInput as json, aKeyFields as array) as character class GqlMutationBuilder
    local cResult := "" as character
    local nI      := 0 as numeric

    for nI := 1 to len(aKeyFields)
        if nI > 1
            cResult += " AND "
        endif
        cResult += aKeyFields[nI] + " = '" + ::escapedValue(oInput[aKeyFields[nI]]) + "'"
    next nI

    return cResult
endmethod

endnamespace
```

- [ ] **Step 2: Compile**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/mutation-builder.tlpp
```
Expected: `Compilation Results .: Total sources(2) Success(2) Errors(0)` (recompiling `query-builder.tlpp` first so `GqlQueryBuilder():EscapeValue()` is a known class in this container session — see Global Constraints on fresh-container recompilation).

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/mutation-builder.tlpp
git commit -m "feat(graphql): add SQL builder for mutation writes"
```

---

### Task 5: `GqlMutationExecutor` — orchestration

**Files:**
- Create: `custom/backoffice/graphql/core/mutation-executor.tlpp`
- Modify: `custom/backoffice/graphql/core/executor.tlpp:22` (declaration line only — add `public`)

**Interfaces:**
- Consumes: `GqlParser():new(cSource as character) as object` / `:parse() as json` / `:getErrors() as array` (existing, unchanged), `GqlMutationSchema:isMutable(cTable as character) as logical` (Task 3), `GqlDictionaryReader:getTableFields(cTable as character) as array` / `:getOrderKey(cTable as character) as character` / `:getFilialField(cTable as character) as character` (existing, Task 2 extended `getTableFields()`), `GqlInputValidator:validateCreate(cTable as character, oInput as json) as array` / `:validateUpdate(...) as array` (Task 2), `GqlMutationBuilder:buildInsert(...)`/`buildUpdate(...)`/`buildSoftDelete(...) as character` (Task 4), `GqlExecutor():new(oSchemaProvider as object, oDictionaryReader as object, oQueryBuilder as object) as object` / `:resolveTableField(oField as json, cExtraWhere as character) as array` (existing, made `public` by Step 1 below — confirmed empirically that an unmarked method crashes uncatchably when called cross-class; see Global Constraints), `GqlErrors():single(cMessage as character) as json` / `:fromArray(aMessages as array) as json` (existing), `TCSqlExec(cStatement as character) as numeric` (native, see Global Constraints), `GqlQueryBuilder():EscapeValue(cValue as character) as character` (existing static).
- Produces: `GqlMutationExecutor():new(oMutationSchema as object, oDictionaryReader as object, oInputValidator as object, oMutationBuilder as object, oExecutor as object) as object`, `GqlMutationExecutor:execute(cQuerySource as character) as json` — same `{"data": {...}}`/`{"errors": [...]}` envelope shape as `GqlExecutor:execute()`. Consumed by the REST entry point in Task 6.

- [ ] **Step 1: Make `GqlExecutor:resolveTableField()` public**

In `custom/backoffice/graphql/core/executor.tlpp`, in the class declaration block, change:
```tlpp
    method resolveTableField(oField as json, cExtraWhere as character) as array
```
to:
```tlpp
    public method resolveTableField(oField as json, cExtraWhere as character) as array
```
This is the only change — the implementation line (`method resolveTableField(...) as array class GqlExecutor`) already has no modifier (implementations never carry one, per the two-part class-syntax rule) and stays exactly as-is. Every other method in this class (`resolveRelation`, `isScalarField`, `fieldNames`, `fieldAlias`) stays unmarked — they're only ever called via `::` from inside `GqlExecutor` itself, never cross-class, so they don't need this change.

- [ ] **Step 2: Compile the modified executor alone first, confirming it still works standalone**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp custom/backoffice/graphql/core/lexer.tlpp custom/backoffice/graphql/core/parser.tlpp custom/backoffice/graphql/core/validator.tlpp custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/core/errors.tlpp custom/backoffice/graphql/core/introspection.tlpp custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
```
Expected: `Compilation Results .: Total sources(11) Success(11) Errors(0)`.

```bash
~/.shared/protheus/compile/scripts/deploy-rpo.sh .
curl -s "http://localhost:9995/rest/graphql?query=%7B%20SA1(limit%3A%201)%20%7B%20A1_COD%20%7D%20%7D"
```
Expected: a real row — proving the visibility change alone doesn't break the existing read path (regression check before adding the new mutation files on top).

- [ ] **Step 3: Write `mutation-executor.tlpp`**

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 3.1.0
@desc GqlMutationExecutor - parses a mutation document, resolves each root
      field to a table+operation (createTABLE/updateTABLE/deleteTABLE),
      validates and writes via GqlInputValidator/GqlMutationBuilder, and
      returns the affected row via the existing read-path executor.
/@*/
class GqlMutationExecutor
    private data oMutationSchema   as object
    private data oDictionaryReader as object
    private data oInputValidator   as object
    private data oMutationBuilder  as object
    private data oExecutor         as object

    public method new(oMutationSchema as object, oDictionaryReader as object, oInputValidator as object, oMutationBuilder as object, oExecutor as object) as object
    public method execute(cQuerySource as character) as json
    method resolveMutationField(oField as json) as json
    method splitFieldName(cName as character) as json
    method keyFieldNames(cTable as character) as array
    method nonKeyPresentFields(cTable as character, oInput as json, aKeyFields as array) as array
    method fetchByKey(cTable as character, oField as json, oInput as json, aKeyFields as array) as array
endclass

method new(oMutationSchema as object, oDictionaryReader as object, oInputValidator as object, oMutationBuilder as object, oExecutor as object) as object class GqlMutationExecutor
    ::oMutationSchema   := oMutationSchema
    ::oDictionaryReader := oDictionaryReader
    ::oInputValidator   := oInputValidator
    ::oMutationBuilder  := oMutationBuilder
    ::oExecutor         := oExecutor
    return self
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cQuerySource Character - raw GraphQL mutation text
@return JSON - {"data": {...}} on success, {"errors": [...]} on failure
/@*/
method execute(cQuerySource as character) as json class GqlMutationExecutor
    local oParser := GqlParser():new(cQuerySource) as object
    local oDoc    as json
    local aDefs   as array
    local aSel    as array
    local oData   as json
    local nI      := 0 as numeric
    local nJ      := 0 as numeric
    local oFieldResult as json
    local oResult as json

    oDoc := oParser:parse()
    if oDoc == nil
        return GqlErrors():fromArray(oParser:getErrors())
    endif

    oData := JsonObject():New()
    aDefs := oDoc["definitions"]
    for nI := 1 to len(aDefs)
        aSel := aDefs[nI]["selectionSet"]
        for nJ := 1 to len(aSel)
            oFieldResult := ::resolveMutationField(aSel[nJ])
            if oFieldResult["errors"] != nil
                return oFieldResult
            endif
            oData[oFieldResult["alias"]] := oFieldResult["row"]
        next nJ
    next nI

    oResult := JsonObject():New()
    oResult["data"] := oData
    return oResult
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param oField JSON - root Field AST node, e.g. createSA1(input: {...})
@return JSON - either {"errors": [...]} (whole-request error, caller
        returns it directly) or {"alias": <character>, "row": <json-or-nil>}
        on success
/@*/
method resolveMutationField(oField as json) as json class GqlMutationExecutor
    local oParsed   := ::splitFieldName(oField["name"]) as json
    local cOp       as character
    local cTable    as character
    local oInputArg as json
    local oInput    as json
    local aErrors   := {} as array
    local aKeyFields as array
    local aSetFields as array
    local aFields   as array
    local aFieldNames as array
    local nI        := 0 as numeric
    local cFilialField as character
    local cSql      as character
    local nStat     := 0 as numeric
    local aExisting as array
    local aRows     as array
    local oOut      as json
    local cAlias    := "" as character

    if oParsed == nil
        return GqlErrors():single("Unknown or restricted mutation: " + oField["name"])
    endif
    cOp    := oParsed["op"]
    cTable := oParsed["table"]

    if !::oMutationSchema:isMutable(cTable)
        return GqlErrors():single("Unknown or restricted mutation: " + oField["name"])
    endif

    oInputArg := oField["arguments"]["input"]
    if oInputArg == nil .or. oInputArg["value"] == nil
        return GqlErrors():single("Mutation '" + oField["name"] + "' requires an 'input' argument")
    endif
    oInput := oInputArg["value"]

    cAlias := oField["name"]
    if oField["alias"] != nil
        cAlias := oField["alias"]
    endif

    aKeyFields := ::keyFieldNames(cTable)
    cFilialField := ::oDictionaryReader:getFilialField(cTable)

    if cOp == "create"
        aErrors := ::oInputValidator:validateCreate(cTable, oInput)
        if len(aErrors) > 0
            return GqlErrors():fromArray(aErrors)
        endif
        aFields := ::oDictionaryReader:getTableFields(cTable)
        aFieldNames := {}
        for nI := 1 to len(aFields)
            if oInput[aFields[nI]["name"]] != nil
                aAdd(aFieldNames, aFields[nI]["name"])
            endif
        next nI
        cSql := ::oMutationBuilder:buildInsert(cTable, cFilialField, oInput, aFieldNames)
        nStat := TCSqlExec(cSql)
        if nStat < 0
            return GqlErrors():single("Write failed for '" + oField["name"] + "'")
        endif
        aRows := ::fetchByKey(cTable, oField, oInput, aKeyFields)
        oOut := JsonObject():New()
        oOut["alias"] := cAlias
        if len(aRows) > 0
            oOut["row"] := aRows[1]
        else
            oOut["row"] := nil
        endif
        return oOut

    elseif cOp == "update"
        for nI := 1 to len(aKeyFields)
            if oInput[aKeyFields[nI]] == nil
                return GqlErrors():single("Missing key field '" + aKeyFields[nI] + "' for update")
            endif
        next nI
        aExisting := ::fetchByKey(cTable, oField, oInput, aKeyFields)
        if len(aExisting) == 0
            return GqlErrors():single("Row not found for update")
        endif
        aErrors := ::oInputValidator:validateUpdate(cTable, oInput)
        if len(aErrors) > 0
            return GqlErrors():fromArray(aErrors)
        endif
        aSetFields := ::nonKeyPresentFields(cTable, oInput, aKeyFields)
        if len(aSetFields) == 0
            return GqlErrors():single("Update requires at least one non-key field")
        endif
        cSql := ::oMutationBuilder:buildUpdate(cTable, cFilialField, oInput, aKeyFields, aSetFields)
        nStat := TCSqlExec(cSql)
        if nStat < 0
            return GqlErrors():single("Write failed for '" + oField["name"] + "'")
        endif
        aRows := ::fetchByKey(cTable, oField, oInput, aKeyFields)
        oOut := JsonObject():New()
        oOut["alias"] := cAlias
        if len(aRows) > 0
            oOut["row"] := aRows[1]
        else
            oOut["row"] := nil
        endif
        return oOut

    elseif cOp == "delete"
        for nI := 1 to len(aKeyFields)
            if oInput[aKeyFields[nI]] == nil
                return GqlErrors():single("Missing key field '" + aKeyFields[nI] + "' for delete")
            endif
        next nI
        aExisting := ::fetchByKey(cTable, oField, oInput, aKeyFields)
        if len(aExisting) == 0
            return GqlErrors():single("Row not found for delete")
        endif
        cSql := ::oMutationBuilder:buildSoftDelete(cTable, cFilialField, oInput, aKeyFields)
        nStat := TCSqlExec(cSql)
        if nStat < 0
            return GqlErrors():single("Write failed for '" + oField["name"] + "'")
        endif
        oOut := JsonObject():New()
        oOut["alias"] := cAlias
        oOut["row"] := aExisting[1]
        return oOut
    endif

    return GqlErrors():single("Unknown or restricted mutation: " + oField["name"])
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@param cName Character - root field name, e.g. "createSA1"
@return JSON - {"op": "create"|"update"|"delete", "table": <character>},
        or nil if cName doesn't start with a known mutation prefix
/@*/
method splitFieldName(cName as character) as json class GqlMutationExecutor
    local oOut as json

    oOut := JsonObject():New()
    if left(cName, 6) == "create"
        oOut["op"] := "create"
        oOut["table"] := substr(cName, 7)
        return oOut
    elseif left(cName, 6) == "update"
        oOut["op"] := "update"
        oOut["table"] := substr(cName, 7)
        return oOut
    elseif left(cName, 6) == "delete"
        oOut["op"] := "delete"
        oOut["table"] := substr(cName, 7)
        return oOut
    endif

    return nil
endmethod

method keyFieldNames(cTable as character) as array class GqlMutationExecutor
    local cKey := ::oDictionaryReader:getOrderKey(cTable) as character
    local aResult := {} as array
    local nI := 0 as numeric
    local nStart := 1 as numeric
    local nComma := 0 as numeric

    nComma := at(",", cKey)
    while nComma > 0
        aAdd(aResult, alltrim(substr(cKey, nStart, nComma - nStart)))
        nStart := nComma + 1
        nComma := at(",", cKey, nStart)
    enddo
    if nStart <= len(cKey)
        aAdd(aResult, alltrim(substr(cKey, nStart)))
    endif

    return aResult
endmethod

method nonKeyPresentFields(cTable as character, oInput as json, aKeyFields as array) as array class GqlMutationExecutor
    local aFields := ::oDictionaryReader:getTableFields(cTable) as array
    local aResult := {} as array
    local nI      := 0 as numeric
    local cName   := "" as character

    for nI := 1 to len(aFields)
        cName := aFields[nI]["name"]
        if ascan(aKeyFields, {|c| c == cName}) > 0
            loop
        endif
        if oInput[cName] != nil
            aAdd(aResult, cName)
        endif
    next nI

    return aResult
endmethod

/*/{Protheus.doc}
@type Method
@author GraphQL Engine Team
@since 3.1.0
@desc Re-selects a single row by key fields, shaped by oField's own
      selectionSet, using the existing read-path executor
      (GqlExecutor:resolveTableField) - never duplicates row-fetch logic.
/@*/
method fetchByKey(cTable as character, oField as json, oInput as json, aKeyFields as array) as array class GqlMutationExecutor
    local cWhere := "" as character
    local nI     := 0 as numeric

    for nI := 1 to len(aKeyFields)
        if nI > 1
            cWhere += " AND "
        endif
        cWhere += aKeyFields[nI] + " = '" + GqlQueryBuilder():EscapeValue(cValToChar(oInput[aKeyFields[nI]])) + "'"
    next nI

    return ::oExecutor:resolveTableField(oField, cWhere)
endmethod

endnamespace
```

- [ ] **Step 4: Compile**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp custom/backoffice/graphql/core/lexer.tlpp custom/backoffice/graphql/core/parser.tlpp custom/backoffice/graphql/core/validator.tlpp custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/core/errors.tlpp custom/backoffice/graphql/core/mutation-schema.tlpp custom/backoffice/graphql/core/input-validator.tlpp custom/backoffice/graphql/core/mutation-builder.tlpp custom/backoffice/graphql/core/mutation-executor.tlpp
```
Expected: `Compilation Results .: Total sources(13) Success(13) Errors(0)` (full dependency chain, including the now-`public` `executor.tlpp` from Step 1 — this may be a fresh container, see Global Constraints).

- [ ] **Step 5: Commit**

```bash
git add custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/core/mutation-executor.tlpp
git commit -m "feat(graphql): add mutation executor orchestrating validate-write-reselect

Makes GqlExecutor:resolveTableField() public so the mutation executor can
reuse it for re-selecting the affected row after a write."
```

---

### Task 6: REST entry point — dispatch mutation vs query

**Files:**
- Modify: `custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp`

**Interfaces:**
- Consumes: `GqlParser():new(cSource as character) as object` / `:parse() as json` / `:getErrors() as array` (existing), `GqlMutationSchema():new(oSchemaProvider as object, oConfig as object) as object` (Task 3), `GqlInputValidator():new(oDictionaryReader as object) as object` (Task 2), `GqlMutationBuilder():new() as object` (Task 4), `GqlMutationExecutor():new(...) as object` / `:execute(cQuerySource as character) as json` (Task 5).

- [ ] **Step 1: Update the entry point to peek the operation type and dispatch**

Replace `custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp`'s body (the `if !empty(cQuery) ... elseif ... else ... endif` block, currently lines 38-45) with:

```tlpp
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
    local oExecutor  as object
    local oPeekParser as object
    local oPeekDoc    as json
    local oMutSchema  as object
    local oMutValidator as object
    local oMutBuilder as object
    local oMutExecutor as object

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
        oPeekParser := custom.backoffice.graphql.GqlParser():new(cQuery)
        oPeekDoc := oPeekParser:parse()
        if oPeekDoc == nil
            oResult := custom.backoffice.graphql.GqlErrors():fromArray(oPeekParser:getErrors())
        elseif len(oPeekDoc["definitions"]) > 0 .and. oPeekDoc["definitions"][1]["operation"] == "mutation"
            oMutSchema    := custom.backoffice.graphql.GqlMutationSchema():new(oSchema, oConfig)
            oMutValidator := custom.backoffice.graphql.GqlInputValidator():new(oDict)
            oMutBuilder   := custom.backoffice.graphql.GqlMutationBuilder():new()
            oExecutor     := custom.backoffice.graphql.GqlExecutor():new(oSchema, oDict, custom.backoffice.graphql.GqlQueryBuilder():new(oConfig))
            oMutExecutor  := custom.backoffice.graphql.GqlMutationExecutor():new(oMutSchema, oDict, oMutValidator, oMutBuilder, oExecutor)
            oResult := oMutExecutor:execute(cQuery)
        else
            oExecutor := custom.backoffice.graphql.GqlExecutor():new(oSchema, oDict, custom.backoffice.graphql.GqlQueryBuilder():new(oConfig))
            oResult := oExecutor:execute(cQuery)
        endif
    elseif !empty(cTypeName)
        oResult := custom.backoffice.graphql.GqlIntrospection():typeDetail(oSchema, cTypeName)
    else
        oResult := custom.backoffice.graphql.GqlIntrospection():schemaNames(oSchema)
    endif

    oRest:setStatusResponse(200, oResult:toJson())

Return .T.
```

(The `query`/no-`query` branches are unchanged from the Core Engine; only the `!empty(cQuery)` branch gained the peek-and-dispatch logic. Parsing `cQuery` twice — once here to peek `operation`, once inside whichever executor's own `execute()` — is intentional: it keeps this plan from touching `parser.tlpp`/`lexer.tlpp`/`executor.tlpp` at all, and query text is short enough that the extra parse is not a real cost.)

- [ ] **Step 2: Compile**

```bash
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp custom/backoffice/graphql/core/lexer.tlpp custom/backoffice/graphql/core/parser.tlpp custom/backoffice/graphql/core/validator.tlpp custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/core/errors.tlpp custom/backoffice/graphql/core/introspection.tlpp custom/backoffice/graphql/core/mutation-schema.tlpp custom/backoffice/graphql/core/input-validator.tlpp custom/backoffice/graphql/core/mutation-builder.tlpp custom/backoffice/graphql/core/mutation-executor.tlpp custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
```
Expected: `Compilation Results .: Total sources(15) Success(15) Errors(0)`.

- [ ] **Step 3: Deploy and verify the query path still works (regression check)**

```bash
~/.shared/protheus/compile/scripts/deploy-rpo.sh .
curl -s "http://localhost:9995/rest/graphql?query=%7B%20SA1(limit%3A%201)%20%7B%20A1_COD%20%7D%20%7D"
```
Expected: `{"data":{"SA1":[{"A1_COD":"..."}]}}` — a real row, proving the peek-and-dispatch logic correctly falls through to the unchanged `GqlExecutor` path for a `query` operation.

- [ ] **Step 4: Commit**

```bash
git add custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
git commit -m "feat(graphql): dispatch mutation operations to GqlMutationExecutor"
```

---

### Task 7: Live verification — create/update/delete against a real table

**Files:**
- None (verification-only task; no code changes)

**Interfaces:**
- Consumes: the full mutation pipeline (Tasks 1-6), already deployed.

- [ ] **Step 1: Verify create**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20createSA1(input%3A%20%7BA1_COD%3A%20%22ZZ0001%22%2C%20A1_LOJA%3A%20%2201%22%2C%20A1_NOME%3A%20%22Mutation%20Test%22%7D)%20%7B%20A1_COD%20A1_NOME%20%7D%20%7D"
```
(URL-decoded: `{ createSA1(input: {A1_COD: "ZZ0001", A1_LOJA: "01", A1_NOME: "Mutation Test"}) { A1_COD A1_NOME } }` — adjust the exact required fields to whatever `curl "http://localhost:9995/rest/graphql?type=SA1"` reports as `required: true`, discovered in Task 2's Step 3 verification.)

Expected: `{"data":{"createSA1":{"A1_COD":"ZZ0001","A1_NOME":"Mutation Test"}}}`.

- [ ] **Step 2: Verify the created row is visible via a normal query**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20SA1(filter%3A%20%5B%7Bfield%3A%20%22A1_COD%22%2C%20op%3A%20%22eq%22%2C%20value%3A%20%22ZZ0001%22%7D%5D)%20%7B%20A1_COD%20A1_NOME%20%7D%20%7D"
```
Expected: the same row, proving the write actually landed and is readable through the unmodified query path.

- [ ] **Step 3: Verify update**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20updateSA1(input%3A%20%7BA1_COD%3A%20%22ZZ0001%22%2C%20A1_LOJA%3A%20%2201%22%2C%20A1_NOME%3A%20%22Updated%20Name%22%7D)%20%7B%20A1_NOME%20%7D%20%7D"
```
Expected: `{"data":{"updateSA1":{"A1_NOME":"Updated Name"}}}`.

- [ ] **Step 4: Verify delete and that it's soft (not a hard delete)**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20deleteSA1(input%3A%20%7BA1_COD%3A%20%22ZZ0001%22%2C%20A1_LOJA%3A%20%2201%22%7D)%20%7B%20A1_COD%20%7D%20%7D"
echo
curl -s "http://localhost:9995/rest/graphql?query=%7B%20SA1(filter%3A%20%5B%7Bfield%3A%20%22A1_COD%22%2C%20op%3A%20%22eq%22%2C%20value%3A%20%22ZZ0001%22%7D%5D)%20%7B%20A1_COD%20%7D%20%7D"
```
Expected: first call returns `{"data":{"deleteSA1":{"A1_COD":"ZZ0001"}}}` (the pre-delete row); second call returns `{"data":{"SA1":[]}}` (no longer visible under the normal `D_E_L_E_T_ = ' '` filter — proves soft-delete, not hard-delete, since a hard delete would look identical from this angle but the point is the row disappears from reads either way; the actual soft-delete confirmation is architectural — `buildSoftDelete()` never emits `DELETE FROM`, verified by code review in Task 4).

- [ ] **Step 5: Verify allow-list rejection**

Temporarily test against a table NOT in `allowMutations` (any denied-for-mutation table, e.g. `SB1` if not allow-listed):
```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20createSB1(input%3A%20%7BB1_COD%3A%20%22ZZ0001%22%7D)%20%7B%20B1_COD%20%7D%20%7D"
```
Expected: `{"errors":[{"message":"Unknown or restricted mutation: createSB1"}]}`.

- [ ] **Step 6: Verify required-field validation**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20createSA1(input%3A%20%7BA1_LOJA%3A%20%2201%22%7D)%20%7B%20A1_COD%20%7D%20%7D"
```
Expected: `{"errors":[{"message":"Field 'A1_COD' is required"}]}` (or whichever fields are actually `required: true` per Task 2's Step 3 output — adjust the omitted field to match).

- [ ] **Step 7: Verify not-found on update/delete**

```bash
curl -s "http://localhost:9995/rest/graphql?query=%7B%20updateSA1(input%3A%20%7BA1_COD%3A%20%22ZZNONE%22%2C%20A1_LOJA%3A%20%2201%22%2C%20A1_NOME%3A%20%22x%22%7D)%20%7B%20A1_NOME%20%7D%20%7D"
```
Expected: `{"errors":[{"message":"Row not found for update"}]}`.

If any expectation in Steps 1-7 doesn't match, this is a plan/code defect to fix before proceeding — do not write the TIR tests in Task 9 against unverified behavior.

---

### Task 8: TIR tests

**Files:**
- Create: `tests/tir/test_graphql_mutation_create.tir`
- Create: `tests/tir/test_graphql_mutation_update.tir`
- Create: `tests/tir/test_graphql_mutation_delete.tir`
- Create: `tests/tir/test_graphql_mutation_denylist.tir`
- Create: `tests/tir/test_graphql_mutation_validation.tir`
- Create: `tests/tir/test_graphql_mutation_notfound.tir`

Same convention as the Core Engine's TIR tests — not locally runnable in this sandbox (`contrib.tir` isn't installed), written for a real Protheus environment with `pytest`, and already verified equivalent-by-hand via the live `curl` checks in Task 7. Follow the exact structure of an existing Core Engine test file as the template.

- [ ] **Step 1: Read an existing test as the template**

```bash
cat tests/tir/test_graphql_filter.tir
```

- [ ] **Step 2: Write `test_graphql_mutation_create.tir`**

```python
import pytest
from tir import Webapp

@pytest.mark.parametrize('mutation, expected_code, expected_name', [
    (
        '{ createSA1(input: {A1_COD: "ZZ0001", A1_LOJA: "01", A1_NOME: "Mutation Test"}) { A1_COD A1_NOME } }',
        'ZZ0001',
        'Mutation Test',
    ),
])
def test_mutation_create(mutation, expected_code, expected_name):
    oHelper = Webapp()
    result = oHelper.GetGraphQL(mutation)
    assert result['data']['createSA1']['A1_COD'] == expected_code
    assert result['data']['createSA1']['A1_NOME'] == expected_name

    verify = oHelper.GetGraphQL(
        '{ SA1(filter: [{field: "A1_COD", op: "eq", value: "' + expected_code + '"}]) { A1_COD A1_NOME } }'
    )
    assert len(verify['data']['SA1']) == 1
    assert verify['data']['SA1'][0]['A1_NOME'] == expected_name

    oHelper.TearDown()
```

(`oHelper.GetGraphQL(...)` mirrors whatever thin HTTP-GET-and-JSON-decode helper the existing Core Engine TIR tests already use against `/rest/graphql?query=...` — reuse that same helper, do not invent a second one.)

- [ ] **Step 3: Write `test_graphql_mutation_update.tir`**

```python
import pytest
from tir import Webapp

def test_mutation_update():
    oHelper = Webapp()

    oHelper.GetGraphQL('{ createSA1(input: {A1_COD: "ZZ0002", A1_LOJA: "01", A1_NOME: "Before"}) { A1_COD } }')

    result = oHelper.GetGraphQL(
        '{ updateSA1(input: {A1_COD: "ZZ0002", A1_LOJA: "01", A1_NOME: "After"}) { A1_NOME } }'
    )
    assert result['data']['updateSA1']['A1_NOME'] == 'After'

    verify = oHelper.GetGraphQL(
        '{ SA1(filter: [{field: "A1_COD", op: "eq", value: "ZZ0002"}]) { A1_COD A1_NOME } }'
    )
    assert verify['data']['SA1'][0]['A1_NOME'] == 'After'
    assert verify['data']['SA1'][0]['A1_COD'] == 'ZZ0002'

    oHelper.TearDown()
```

- [ ] **Step 4: Write `test_graphql_mutation_delete.tir`**

```python
import pytest
from tir import Webapp

def test_mutation_delete():
    oHelper = Webapp()

    oHelper.GetGraphQL('{ createSA1(input: {A1_COD: "ZZ0003", A1_LOJA: "01", A1_NOME: "ToDelete"}) { A1_COD } }')

    result = oHelper.GetGraphQL('{ deleteSA1(input: {A1_COD: "ZZ0003", A1_LOJA: "01"}) { A1_COD } }')
    assert result['data']['deleteSA1']['A1_COD'] == 'ZZ0003'

    verify = oHelper.GetGraphQL(
        '{ SA1(filter: [{field: "A1_COD", op: "eq", value: "ZZ0003"}]) { A1_COD } }'
    )
    assert len(verify['data']['SA1']) == 0

    oHelper.TearDown()
```

- [ ] **Step 5: Write `test_graphql_mutation_denylist.tir`**

```python
import pytest
from tir import Webapp

def test_mutation_denylist():
    oHelper = Webapp()

    result = oHelper.GetGraphQL('{ createSB1(input: {B1_COD: "ZZ0001"}) { B1_COD } }')
    assert 'errors' in result
    assert 'Unknown or restricted mutation' in result['errors'][0]['message']

    oHelper.TearDown()
```

- [ ] **Step 6: Write `test_graphql_mutation_validation.tir`**

```python
import pytest
from tir import Webapp

@pytest.mark.parametrize('mutation, expected_fragment', [
    ('{ createSA1(input: {A1_LOJA: "01"}) { A1_COD } }', "is required"),
])
def test_mutation_validation(mutation, expected_fragment):
    oHelper = Webapp()
    result = oHelper.GetGraphQL(mutation)
    assert 'errors' in result
    assert expected_fragment in result['errors'][0]['message']
    oHelper.TearDown()
```

- [ ] **Step 7: Write `test_graphql_mutation_notfound.tir`**

```python
import pytest
from tir import Webapp

def test_mutation_update_not_found():
    oHelper = Webapp()
    result = oHelper.GetGraphQL(
        '{ updateSA1(input: {A1_COD: "ZZNONE", A1_LOJA: "01", A1_NOME: "x"}) { A1_NOME } }'
    )
    assert 'errors' in result
    assert 'Row not found for update' in result['errors'][0]['message']
    oHelper.TearDown()

def test_mutation_delete_not_found():
    oHelper = Webapp()
    result = oHelper.GetGraphQL(
        '{ deleteSA1(input: {A1_COD: "ZZNONE", A1_LOJA: "01"}) { A1_COD } }'
    )
    assert 'errors' in result
    assert 'Row not found for delete' in result['errors'][0]['message']
    oHelper.TearDown()
```

- [ ] **Step 8: Commit**

```bash
git add tests/tir/test_graphql_mutation_create.tir tests/tir/test_graphql_mutation_update.tir tests/tir/test_graphql_mutation_delete.tir tests/tir/test_graphql_mutation_denylist.tir tests/tir/test_graphql_mutation_validation.tir tests/tir/test_graphql_mutation_notfound.tir
git commit -m "test(graphql): add TIR tests for mutations"
```

---

### Task 9: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/configuration.md`

- [ ] **Step 1: Add mutations to the README example section**

In `README.md`, after the existing `## Example` section, add:

```markdown
## Mutations

`createTABLE`/`updateTABLE`/`deleteTABLE` are exposed only for tables
listed in `config/graphql-config.json`'s `allowMutations` (empty by
default — nothing is writable until an admin opts a table in). Delete is
always soft (`D_E_L_E_T_ = '*'`), never a real row removal.

```
mutation { createSA1(input: {A1_COD: "000123", A1_LOJA: "01", A1_NOME: "Foo"}) {
    A1_COD
    A1_NOME
} }
```

See `docs/architecture.md` and
`docs/superpowers/specs/2026-08-14-graphql-mutations-design.md`.
```

- [ ] **Step 2: Update the sub-project roadmap line**

In `README.md`, change:
```markdown
This is sub-project 1 of 6: Core Engine (this repo) → Mutations → Auth →
Field Hooks → SDK Generator → Console PO-UI. See the design spec for the
full roadmap and how each later sub-project plugs into this engine.
```
to:
```markdown
This is sub-projects 1-2 of 6: Core Engine + Mutations (this repo) → Auth →
Field Hooks → SDK Generator → Console PO-UI. See the design specs for the
full roadmap and how each later sub-project plugs into this engine.
```

- [ ] **Step 3: Add mutations architecture section**

In `docs/architecture.md`, after the existing Core Engine content, add:

```markdown
## Mutations

`GqlMutationExecutor` (core/mutation-executor.tlpp) is a parallel write
pipeline alongside the read executor, sharing the same lexer/parser and
the same `GqlDictionaryReader`/`GqlQueryBuilder`. It writes via
`TCSqlExec()` — **not** `TCQuery`, which crashes uncatchably on anything
but `SELECT` in this environment (confirmed empirically; see the plan's
Global Constraints for the full investigation) — and re-selects the
affected row through the existing `GqlExecutor:resolveTableField()` so
response shaping (aliases, nested selections) is never duplicated.

A table is writable only if it's in `allowMutations` (config) AND still
passes the read-path deny-list — the two gates combine, neither alone is
sufficient. `GqlInputValidator` checks required/type/length against SX3
metadata before any SQL runs. Delete is always soft
(`D_E_L_E_T_ = '*'`), matching how every query already filters reads.
```

- [ ] **Step 4: Document the `allowMutations` config key**

In `docs/configuration.md`, add a section documenting `allowMutations`: exact table aliases (no wildcard, unlike `denyTables`/`denyFields`), empty by default, and the combined-gate behavior with `denyTables`.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture.md docs/configuration.md
git commit -m "docs(graphql): document mutations usage and configuration"
```

---

### Task 10: Final cleanup verification

**Files:**
- None (verification-only task)

- [ ] **Step 1: Confirm no scratch/probe files remain**

```bash
git status --porcelain
ls /home/peder/Projetos/GraphQL/wtest.tlpp 2>&1
```
Expected: clean working tree, `wtest.tlpp` not found.

- [ ] **Step 2: Full recompile from a fresh container, confirming the entire project (Core Engine + Mutations) still compiles clean together**

```bash
docker rm -f protheus-compile 2>/dev/null
~/.shared/protheus/compile/scripts/compile.sh . custom/backoffice/graphql/core/config.tlpp custom/backoffice/graphql/core/access-control.tlpp custom/backoffice/graphql/core/dictionary-reader.tlpp custom/backoffice/graphql/core/schema-provider.tlpp custom/backoffice/graphql/core/lexer.tlpp custom/backoffice/graphql/core/parser.tlpp custom/backoffice/graphql/core/validator.tlpp custom/backoffice/graphql/core/query-builder.tlpp custom/backoffice/graphql/core/executor.tlpp custom/backoffice/graphql/core/errors.tlpp custom/backoffice/graphql/core/introspection.tlpp custom/backoffice/graphql/core/mutation-schema.tlpp custom/backoffice/graphql/core/input-validator.tlpp custom/backoffice/graphql/core/mutation-builder.tlpp custom/backoffice/graphql/core/mutation-executor.tlpp custom/backoffice/graphql/entrypoints/service.entrypoint.tlpp
```
Expected: `Compilation Results .: Total sources(16) Success(16) Errors(0)`.

- [ ] **Step 3: Redeploy and re-run the full Task 7 verification sequence once more**

```bash
~/.shared/protheus/compile/scripts/deploy-rpo.sh .
```
Re-run every `curl` from Task 7, Steps 1-7. All expectations must still hold on this final, from-clean-container build.

- [ ] **Step 4: Clean up the local `build/` directory (git-ignored, not part of the commit)**

```bash
rm -rf /home/peder/Projetos/GraphQL/build
```
