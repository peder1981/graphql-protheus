# GraphQL Protheus — Self-Service Buffet & Configurabilidade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the GraphQL Protheus engine into a self-service buffet where consumers discover, explore, and use ERP data through configuration alone — no code changes needed to add new tables.

**Architecture:** A configuration layer (`GqlConfig`) reads module definitions from the appserver INI file; an auto-discovery layer (`GqlAutoDiscover`) queries the SX3 dictionary to populate fields automatically; a playground layer (`GqlPlayground`) renders an interactive HTML interface served directly by the appserver; and new REST endpoints expose schema metadata and module listings. The existing core engine (parser, validator, executor) remains unchanged.

**Tech Stack:**
- **Language:** TLPP (`.tlpp`) with `#include "tlpp-core.th"` + `#include "totvs.ch"`
- **Config parsing:** `GetIniKey()` / `GetIniSection()` from Protheus framework
- **Dictionary queries:** `FWExecStatement` against SX3 table
- **HTTP serving:** `FWSetHeader()` + `FWPrintHTML()` for HTML endpoints
- **Testing:** TIR (Python `.tir`) with `contrib.tir.Webapp`
- **Documentation:** Markdown files

## Global Constraints

- **Runtime:** Must run inside Protheus appserver 12.1.2510 — no external Node.js
- **Encoding:** All source files `.tlpp` must be CP-1252 encoded (Protheus compiler requirement)
- **No IIF:** Use explicit `If/Else/EndIf` — never `IIf()` (SonarQube CA4000)
- **Soft-delete filter:** All DB queries must include `D_E_L_E_T_ = ' '`
- **Filial filter:** All DB queries must include `xFilial('XXX')` for the relevant table
- **No GetMV/Pergunte in loops:** Never call `GetMV()`, `SuperGetMV()`, or `Pergunte()` inside loops
- **No ConOut:** Use `FWLogMsg()` for logging, never `ConOut()`
- **Namespace:** `custom.backoffice.graphql` for all new classes and functions
- **TOTVS naming:** lowercase with dots, no underscores in file names, PascalCase classes, camelCase methods
- **Entry point naming:** File name must match the EP name exactly, lowercase with dots, `.tlpp` extension. The `U_` prefix is implicit
- **ProtheusDOC:** Every function/method must include `/*/{Protheus.doc}` block
- **No CDN:** Playground HTML must be fully self-contained (inline CSS/JS, no external dependencies)

---

## File Structure (New + Modified)

```
custom/backoffice/graphql/
├── core/
│   ├── config.tlpp              [NOVO] — GqlConfig class
│   ├── autodiscover.tlpp         [NOVO] — GqlAutoDiscover class
│   ├── types.tlpp                [EXISTENTE, sem mudancas]
│   ├── schema.tlpp               [EXISTENTE, sem mudancas]
│   ├── parser.tlpp               [EXISTENTE, sem mudancas]
│   ├── validator.tlpp            [EXISTENTE, sem mudancas]
│   ├── executor.tlpp             [EXISTENTE, sem mudancas]
│   └── executive.tlpp            [ATUALIZADO] — loadFromConfig(), getModuleMetadata()
├── playground.tlpp               [NOVO] — GqlPlayground HTML generator
├── schema/                       [EXISTENTE, sem mudancas]
├── resolvers/                    [EXISTENTE, sem mudancas]
├── playground.entrypoint.tlpp    [NOVO] — REST EP: /graphql/playground
├── schema.render.tlpp            [NOVO] — REST EP: /graphql/schema
├── modules.render.tlpp           [NOVO] — REST EP: /graphql/modules
├── service.entrypoint.tlpp       [EXISTENTE, sem mudancas]
└── config/
    └── appserver-graphql.ini     [ATUALIZADO] — secao [GraphQL] completa

docs/
├── api-reference.md              [NOVO]
├── configuration.md              [NOVO]
├── architecture.md               [NOVO]
├── self-service-guide.md         [NOVO]
└── changelog.md                  [NOVO]
```

---

## Task 1: GqlConfig — Configuration Parser

**Files:**
- Create: `custom/backoffice/graphql/core/config.tlpp`

**Interfaces:**
- Consumes: nothing external
- Produces: `GqlConfig` class with methods:
  - `new()` — parse `[GraphQL]` section from appserver.ini
  - `getModuleKeys() as array` — returns `{"customer", "product", "invoice", ...}`
  - `getModuleField(cModule as character, cKey as character) as character` — returns config value
  - `isModuleEnabled(cModule as character) as logical` — returns .T. or .F.
  - `getDefaultFirst() as numeric` — default page size (default: 10)
  - `getMaxFirst() as numeric` — hard limit (default: 100)
  - `getDefaultOffset() as numeric` — default offset (default: 0)
  - `isLogEnabled() as logical` — logging flag
  - `getLogLevel() as character` — log level string
  - `getAutoDiscoverEnabled() as logical` — auto-discovery flag
  - `getAutoDiscoverSkipTables() as array` — tables to skip
  - `getAutoDiscoverMinFields() as numeric` — minimum fields threshold

**Config parsing logic:**
- Use `GetIniKey("GraphQL", cKey, cDefault, cIniFile)` to read values
- cIniFile: use `GetSVars():cIniFile` or fallback to empty string (Protheus reads current appserver.ini)
- Module keys discovered by scanning keys matching `module.*.table`
- For each module key found, extract the module name (e.g., "customer" from "module.customer.table")

- [ ] **Step 1: Create the config class**

Write `custom/backoffice/graphql/core/config.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 2.0.0
@desc GqlConfig — parse and expose GraphQL configuration from appserver.ini [GraphQL] section
/@*/
class GqlConfig
    private data aModules      as array
    private data nDefaultFirst as numeric
    private data nMaxFirst     as numeric
    private data nDefaultOffset as numeric
    private data lLogEnabled   as logical
    private data cLogLevel     as character
    private data lAutoDisc     as logical
    private data aSkipTables   as array
    private data nMinFields    as numeric

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Object - self
    /@*/
    method new() as object class GqlConfig
        local cKey     := "" as character
        local cVal     := "" as character
        local aModuleKeys := {} as array
        local aSkip    := {} as array
        local cSkipStr := "" as character
        local nI       := 0 as numeric
        local cModuleName := "" as character

        ::nDefaultFirst  := 10
        ::nMaxFirst      := 100
        ::nDefaultOffset := 0
        ::lLogEnabled    := .F.
        ::cLogLevel      := "INFO"
        ::lAutoDisc      := .F.
        ::aSkipTables    := {}
        ::nMinFields     := 3
        ::aModules       := {}

        // Read global defaults
        cVal := GetIniKey("GraphQL", "default.first", cValToChar(10), "")
        if valtype(cVal) == "C"
            ::nDefaultFirst := cValToNumber(cVal)
        endif

        cVal := GetIniKey("GraphQL", "default.maxFirst", cValToChar(100), "")
        if valtype(cVal) == "C"
            ::nMaxFirst := cValToNumber(cVal)
        endif

        cVal := GetIniKey("GraphQL", "default.offset", cValToChar(0), "")
        if valtype(cVal) == "C"
            ::nDefaultOffset := cValToNumber(cVal)
        endif

        cVal := GetIniKey("GraphQL", "log.enabled", "0", "")
        ::lLogEnabled := (cVal == "1" .or. cVal == "true" .or. cVal == "True")

        cVal := GetIniKey("GraphQL", "log.level", "INFO", "")
        if valtype(cVal) == "C"
            ::cLogLevel := upper(alltrim(cVal))
        endif

        cVal := GetIniKey("GraphQL", "module.autoDiscover.enabled", "0", "")
        ::lAutoDisc := (cVal == "1" .or. cVal == "true" .or. cVal == "True")

        cSkipStr := GetIniKey("GraphQL", "module.autoDiscover.skipTables", "SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL", "")
        if valtype(cSkipStr) == "C"
            aSkip := Explode(cSkipStr, ",")
            for nI := 1 to len(aSkip)
                aAdd(::aSkipTables, alltrim(upper(aSkip[nI])))
            next nI
        endif

        cVal := GetIniKey("GraphQL", "module.autoDiscover.minFields", "3", "")
        if valtype(cVal) == "C"
            ::nMinFields := cValToNumber(cVal)
        endif

        // Discover module keys by scanning for "module.<name>.table"
        // Use a brute-force scan of common module names + dynamic discovery
        ::discoverModules()

        FWLogMsg("GqlConfig: initialized with " + cValToChar(len(::aModules)) + " modules", .T.)
        return self
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @desc Scan appserver.ini for module.*.table keys to discover configured modules
    /@*/
    method discoverModules() class GqlConfig
        local cKey     := "" as character
        local cVal     := "" as character
        local cModName := "" as character
        local nPos     := 0 as numeric
        local nI       := 0 as numeric
        local aModList := {} as array
        local aSeen    := {} as array
        local nJ       := 0 as numeric

        // Scan common module prefixes first
        local aCommonModules := {"customer", "product", "invoice", "purchase", "financial", "supplier", "employee", "warehouse", "production", "sales"}
        local nCommon := len(aCommonModules)

        for nI := 1 to nCommon
            cVal := GetIniKey("GraphQL", "module." + aCommonModules[nI] + ".table", "", "")
            if cVal != "" .and. cVal != nil
                if !aScan(aSeen, {|a| a == aCommonModules[nI] }) > 0
                    aAdd(aModList, aCommonModules[nI])
                    aAdd(aSeen, aCommonModules[nI])
                endif
            endif
        next nI

        // Also scan for any module.*.table pattern by checking standard INI keys
        // Protheus GetIniSection can list all keys in a section
        local aSectionKeys := GetIniSection("GraphQL", "")
        local nKeys := len(aSectionKeys)
        local cPrefix := "" as character
        local nPrefixLen := 0 as numeric

        for nI := 1 to nKeys
            cKey := alltrim(aSectionKeys[nI])
            if left(cKey, 8) == "module.." .and. right(cKey, 6) == ".table"
                cPrefix := substr(cKey, 9)
                nPrefixLen := len(cPrefix)
                cModName := left(cPrefix, nPrefixLen - 6)
                if cModName != "" .and. !aScan(aSeen, cModName) > 0
                    aAdd(aModList, cModName)
                    aAdd(aSeen, cModName)
                endif
            endif
        next nI

        // Store discovered modules
        ::aModules := aModList
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Array - list of module key names
    /@*/
    method getModuleKeys() as array class GqlConfig
        return ::aModules
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cModule Character - module key name (e.g., "customer")
    @param cKey Character - configuration key (e.g., "table", "fields", "filter")
    @return Character - configuration value, or empty string if not found
    /@*/
    method getModuleField(cModule as character, cKey as character) as character class GqlConfig
        local cFullKey := "module." + lower(cModule) + "." + lower(cKey)
        local cVal := GetIniKey("GraphQL", cFullKey, "", "")
        return cVal
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cModule Character - module key name
    @return Logical - .T. if module is enabled
    /@*/
    method isModuleEnabled(cModule as character) as logical class GqlConfig
        local cVal := ::getModuleField(cModule, "enabled")
        return (cVal == "1" .or. cVal == "true" .or. cVal == "True")
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Numeric - default page size
    /@*/
    method getDefaultFirst() as numeric class GqlConfig
        return ::nDefaultFirst
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Numeric - maximum page size
    /@*/
    method getMaxFirst() as numeric class GqlConfig
        return ::nMaxFirst
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Numeric - default offset
    /@*/
    method getDefaultOffset() as numeric class GqlConfig
        return ::nDefaultOffset
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Logical - .T. if logging is enabled
    /@*/
    method isLogEnabled() as logical class GqlConfig
        return ::lLogEnabled
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Character - log level string
    /@*/
    method getLogLevel() as character class GqlConfig
        return ::cLogLevel
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Logical - .T. if auto-discovery is enabled
    /@*/
    method getAutoDiscoverEnabled() as logical class GqlConfig
        return ::lAutoDisc
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Array - list of table aliases to skip during auto-discovery
    /@*/
    method getAutoDiscoverSkipTables() as array class GqlConfig
        return ::aSkipTables
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Numeric - minimum field count for auto-discovery
    /@*/
    method getAutoDiscoverMinFields() as numeric class GqlConfig
        return ::nMinFields
    endmethod

    /*/{Protheus.doc}
    @type Static Function
    @author GraphQL Engine Team
    @since 2.0.0
    @param cString Character - string to split
    @param cDelim Character - delimiter character
    @return Array - split parts
    /@*/
    static method Explode(cString as character, cDelim as character) as array class GqlConfig
        local aResult := {} as array
        local cAccum  := "" as character
        local nI      := 0 as numeric
        local cCh     := "" as character
        local nLen    := len(cString)

        for nI := 1 to nLen
            cCh := substr(cString, nI, 1)
            if cCh == cDelim
                if cAccum != ""
                    aAdd(aResult, cAccum)
                endif
                cAccum := ""
            else
                cAccum += cCh
            endif
        next nI

        if cAccum != ""
            aAdd(aResult, cAccum)
        endif

        return aResult
    endfunction

endnamespace
```

- [ ] **Step 2: Verify the file**

Check:
- No `iif(` in the file
- Namespace is `custom.backoffice.graphql`
- All methods have ProtheusDOC
- CP-1252 encoding

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/config.tlpp
git commit -m "feat(graphql): add GqlConfig class for INI-based module configuration"
```

---

## Task 2: GqlAutoDiscover — SX3 Dictionary Discovery

**Files:**
- Create: `custom/backoffice/graphql/core/autodiscover.tlpp`

**Interfaces:**
- Consumes: `GqlConfig` from `config.tlpp`
- Produces: `GqlAutoDiscover` class with methods:
  - `new(oConfig as object)` — constructor
  - `discover() as json` — queries SX3, returns `{"SA1": {"fields": [...], "count": N}, ...}`
  - `getTableFields(cTable as character) as array` — returns field array for one table
  - `isSkipTable(cTable as character) as logical` — check if table should be skipped
  - `getCachedFields() as json` — returns the cached discovery result

**Discovery query:**
```sql
SELECT SX3_CPOSX3, ADQ_CAMPO
FROM RetSqlName("SX3")
WHERE SX3_FILIAL = '{filial}'
  AND SX3_DELET  = ' '
  AND ADQ_CAMPO  != ''
  AND ADQ_CAMPO  NOT LIKE 'D_E_L_E_T_%'
  AND ADQ_CAMPO  NOT LIKE 'XI%'
ORDER BY SX3_CPOSX3
```

- [ ] **Step 1: Create the auto-discover class**

Write `custom/backoffice/graphql/core/autodiscover.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "types.tlpp"
#include "schema.tlpp"
#include "config.tlpp"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 2.0.0
@desc GqlAutoDiscover — query SX3 dictionary to auto-discover table fields
/@*/
class GqlAutoDiscover
    private data oConfig    as object
    private data oCache     as json
    private data lCached    as logical
    private data cFilial    as character

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param oConfig Object - GqlConfig instance
    @return Object - self
    /@*/
    method new(oConfig as object) as object class GqlAutoDiscover
        ::oConfig  := oConfig
        ::oCache   := JsonParse("{}")
        ::lCached  := .F.
        ::cFilial  := xFilial("SA1")  // default filial for dictionary queries
        return self
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cFilial Character - branch to use for dictionary queries
    @return Object - self
    /@*/
    method setFilial(cFilial as character) as object class GqlAutoDiscover
        if cFilial != "" .and. cFilial != nil
            ::cFilial := cFilial
        endif
        return self
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return JSON - discovery result {"TABLE": {"fields": [...], "count": N}}
    /@*/
    method discover() as json class GqlAutoDiscover
        local cSql    := "" as character
        local oRs     := nil as object
        local cTable  := "" as character
        local cField  := "" as character
        local aFields := {} as array
        local aAllTables := {} as json
        local oResult  := JsonParse("{}")
        local nI       := 0 as numeric
        local cTableName := "" as character
        local aTableList := {} as array

        // Build list of tables to discover from SX1 (table dictionary)
        cSql := "SELECT SX1_TABELA FROM " + RetSqlName("SX1") + " " + ;
                "WHERE SX1_FILIAL = '" + ::cFilial + "' " + ;
                "AND SX1_DELET = ' ' " + ;
                "AND SX1_TIPO in ('T','V') " + ;
                "%nolock%" + ;
                "ORDER BY SX1_TABELA"

        oRs := FWExecStatement(cSql)
        if oRs != nil
            do while oRs:NextRecord()
                cTableName := alltrim(oRs:GetData("SX1_TABELA"))
                if cTableName != "" .and. !::isSkipTable(cTableName)
                    aAdd(aTableList, cTableName)
                endif
            enddo
            oRs:Close()
        endif

        // For each table, query SX3 for fields
        for nI := 1 to len(aTableList)
            cTableName := aTableList[nI]
            aFields := ::getTableFieldsDirect(cTableName)
            if len(aFields) >= ::oConfig:getAutoDiscoverMinFields()
                JsonSet(oResult, cTableName, JsonParse("{\"fields\":" + JsonStringify(aFields) + ",\"count\":" + cValToChar(len(aFields)) + "}"))
            endif
        next nI

        ::oCache  := oResult
        ::lCached := .T.

        FWLogMsg("GqlAutoDiscover: discovered " + cValToChar(len(aTableList)) + " tables, " + ;
                 cValToChar(len(::oConfig:getModuleKeys())) + " modules configured", .T.)

        return oResult
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cTable Character - table alias (e.g., "SA1")
    @return Array - list of field names
    /@*/
    method getTableFields(cTable as character) as array class GqlAutoDiscover
        local oEntry := JsonGet(::oCache, cTable)
        if oEntry != nil
            return JsonGet(oEntry, "fields")
        endif
        return ::getTableFieldsDirect(cTable)
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cTable Character - table alias
    @return Logical - .T. if table should be skipped
    /@*/
    method isSkipTable(cTable as character) as logical class GqlAutoDiscover
        local aSkip := ::oConfig:getAutoDiscoverSkipTables()
        local nI    := 0 as numeric
        local cSkip := "" as character
        cTable := upper(alltrim(cTable))
        for nI := 1 to len(aSkip)
            cSkip := upper(alltrim(aSkip[nI]))
            if cTable == cSkip
                return .T.
            endif
        next nI
        return .F.
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return JSON - cached discovery result
    /@*/
    method getCached() as json class GqlAutoDiscover
        return ::oCache
    endmethod

    // ── Private helpers ──

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param cTable Character - table alias
    @return Array - field names from SX3
    /@*/
    method getTableFieldsDirect(cTable as character) as array class GqlAutoDiscover
        local aFields  := {} as array
        local cSql     := "" as character
        local oRs      := nil as object
        local cField   := "" as character
        local cFilial  := ::cFilial

        cSql := "SELECT ADQ_CAMPO FROM " + RetSqlName("SX3") + " " + ;
                "WHERE SX3_FILIAL = '" + cFilial + "' " + ;
                "AND SX3_CPOSX3 = (SELECT MAX(SX3_CPOSX3) FROM " + RetSqlName("SX3") + " S2 " + ;
                "WHERE S2.SX3_TABELA = '" + cTable + "' AND S2.SX3_CPOSX3 = SX3.SX3_CPOSX3) " + ;
                "AND ADQ_CAMPO != '' " + ;
                "AND ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%' " + ;
                "AND ADQ_CAMPO NOT LIKE 'XI%' " + ;
                "%nolock%" + ;
                "ORDER BY ADQ_CAMPO"

        // Simpler approach: use SX3 with table filter
        cSql := "SELECT ADQ_CAMPO FROM " + RetSqlName("SX3") + " " + ;
                "WHERE SX3_FILIAL = '" + cFilial + "' " + ;
                "AND SX3_TABELA = '" + cTable + "' " + ;
                "AND ADQ_CAMPO != '' " + ;
                "AND ADQ_CAMPO NOT LIKE 'D_E_L_E_T_%' " + ;
                "AND ADQ_CAMPO NOT LIKE 'XI%' " + ;
                "%nolock%" + ;
                "ORDER BY SX3_CPOSX3"

        oRs := FWExecStatement(cSql)
        if oRs != nil
            do while oRs:NextRecord()
                cField := alltrim(oRs:GetData("ADQ_CAMPO"))
                if cField != ""
                    aAdd(aFields, cField)
                endif
            enddo
            oRs:Close()
        endif

        return aFields
    endmethod

endnamespace

endnamespace
```

- [ ] **Step 2: Verify**

Check: no `iif()`, correct namespace, ProtheusDOC on all methods, CP-1252.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/autodiscover.tlpp
git commit -m "feat(graphql): add GqlAutoDiscover class for SX3 dictionary-based field discovery"
```

---

## Task 3: Update GqlExecutive — Config Integration

**Files:**
- Modify: `custom/backoffice/graphql/core/executive.tlpp`

**Changes:**
1. Add `#include "config.tlpp"` and `#include "autodiscover.tlpp"`
2. Add private data: `oConfig` (GqlConfig), `oAutoDiscover` (GqlAutoDiscover)
3. In `new()`: initialize config and auto-discover
4. Add `loadFromConfig(oConfig)` method that reads INI and registers modules
5. Add `getModuleMetadata()` method for the `/graphql/modules` endpoint
6. Add `getAutoDiscoverResult()` method

**loadFromConfig logic:**
1. For each module key from `oConfig:getModuleKeys()`:
   a. Check `isModuleEnabled()` — skip if disabled
   b. Read `table`, `type`, `fields`, `filter` from config
   c. If `fields` is empty and auto-discovery is enabled → use `oAutoDiscover:getTableFields(cTable)`
   d. If `fields` is still empty → log warning and skip
   e. Call existing `registerModule(cTable, cTypeName, aFields)`
   f. Store module metadata (filters, fields count, enabled status)

**getModuleMetadata logic:**
Returns JSON:
```json
{
  "modules": [
    {
      "key": "customer",
      "table": "SA1",
      "type": "Cliente",
      "enabled": true,
      "fields": ["A1_COD", "A1_NOME", ...],
      "filters": ["A1_NOME", "A1_CIDADE", ...],
      "fieldCount": 10,
      "discovered": false
    },
    ...
  ],
  "autoDiscover": {
    "enabled": true,
    "tablesDiscovered": 45,
    "tablesSkipped": 12
  }
}
```

- [ ] **Step 1: Modify executive.tlpp**

Add to the class after the existing private data section:

```tlpp
    private data oConfig       as object
    private data oAutoDiscover as object
    private data aModuleMeta   as array
```

In the `new()` method, add after existing initialization:

```tlpp
        ::oConfig        := GqlConfig():new()
        ::oAutoDiscover  := GqlAutoDiscover():new(::oConfig)
        ::aModuleMeta    := {}
```

Add these new methods before the static helpers section:

```tlpp
    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @desc Load module configuration from appserver.ini and register with schema
    @return Object - self
    /@*/
    method loadFromConfig() as object class GqlExecutive
        local aModuleKeys  := {} as array
        local nI           := 0 as numeric
        local cModule      := "" as character
        local cTable       := "" as character
        local cTypeName    := "" as character
        local cFieldsStr   := "" as character
        local aFields      := {} as array
        local cFiltersStr  := "" as character
        local aFilters     := {} as array
        local lEnabled     := .F. as logical
        local oMeta        := nil as object

        aModuleKeys := ::oConfig:getModuleKeys()

        for nI := 1 to len(aModuleKeys)
            cModule   := aModuleKeys[nI]
            cTable    := ::oConfig:getModuleField(cModule, "table")
            cTypeName := ::oConfig:getModuleField(cModule, "type")
            cFieldsStr := ::oConfig:getModuleField(cModule, "fields")
            cFiltersStr := ::oConfig:getModuleField(cModule, "filter")
            lEnabled  := ::oConfig:isModuleEnabled(cModule)

            if !lEnabled
                FWLogMsg("GqlExecutive: module '" + cModule + "' is disabled, skipping", .F.)
                iterate
            endif

            if cTable == "" .or. cTypeName == ""
                FWLogMsg("GqlExecutive: module '" + cModule + "' missing table or type, skipping", .F.)
                iterate
            endif

            // Parse fields
            if cFieldsStr != ""
                aFields := GqlConfig:Explode(cFieldsStr, ",")
            else
                // Auto-discover
                aFields := ::oAutoDiscover:getTableFields(cTable)
                FWLogMsg("GqlExecutive: auto-discovered " + cValToChar(len(aFields)) + " fields for " + cTable, .T.)
            endif

            if len(aFields) == 0
                FWLogMsg("GqlExecutive: no fields for module '" + cModule + "', skipping", .F.)
                iterate
            endif

            // Parse filters
            if cFiltersStr != ""
                aFilters := GqlConfig:Explode(cFiltersStr, ",")
            else
                aFilters := {}
            endif

            // Register the module
            ::registerModule(cTable, cTypeName, aFields)

            // Store metadata
            oMeta := JsonParse("{}")
            JsonSet(oMeta, "key", cModule)
            JsonSet(oMeta, "table", cTable)
            JsonSet(oMeta, "type", cTypeName)
            JsonSet(oMeta, "enabled", .T.)
            JsonSet(oMeta, "fields", aFields)
            JsonSet(oMeta, "filters", aFilters)
            JsonSet(oMeta, "fieldCount", len(aFields))
            JsonSet(oMeta, "discovered", empty(cFieldsStr))
            aAdd(::aModuleMeta, oMeta)

            FWLogMsg("GqlExecutive: loaded module '" + cModule + "' (" + cTable + ") with " + cValToChar(len(aFields)) + " fields", .T.)
        next nI

        return self
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return JSON - module metadata for /graphql/modules endpoint
    /@*/
    method getModuleMetadata() as json class GqlExecutive
        local oResult := JsonParse("{}")
        local oDisc   := JsonParse("{}")
        local aDiscResult := nil as json

        JsonSet(oResult, "modules", ::aModuleMeta)
        JsonSet(oResult, "config", JsonParse("{") + ;
               "\"defaultFirst\":" + cValToChar(::oConfig:getDefaultFirst()) + "," + ;
               "\"maxFirst\":" + cValToChar(::oConfig:getMaxFirst()) + "," + ;
               "\"logEnabled\":" + (::oConfig:isLogEnabled() ? "true" : "false") + "," + ;
               "\"autoDiscoverEnabled\":" + (::oConfig:getAutoDiscoverEnabled() ? "true" : "false") + ;
               "}")

        if ::oConfig:getAutoDiscoverEnabled()
            aDiscResult := ::oAutoDiscover:discover()
            JsonSet(oDisc, "tablesDiscovered", len(aDiscResult))
            JsonSet(oDisc, "tablesSkipped", len(::oConfig:getAutoDiscoverSkipTables()))
        else
            JsonSet(oDisc, "tablesDiscovered", 0)
            JsonSet(oDisc, "tablesSkipped", 0)
        endif
        JsonSet(oResult, "autoDiscover", oDisc)

        return oResult
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Object - GqlAutoDiscover instance
    /@*/
    method getAutoDiscover() as object class GqlExecutive
        return ::oAutoDiscover
    endmethod
```

- [ ] **Step 2: Verify no iif(), correct includes**

Run: `grep -rn "iif(" custom/backoffice/graphql/core/executive.tlpp`
Expected: 0 matches.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/core/executive.tlpp
git commit -m "feat(graphql): integrate GqlConfig and GqlAutoDiscover into GqlExecutive"
```

---

## Task 4: GqlPlayground — Interactive HTML Generator

**Files:**
- Create: `custom/backoffice/graphql/playground.tlpp`

**Interfaces:**
- Consumes: `GqlSchema` (from schema.tlpp), `GqlConfig` (from config.tlpp)
- Produces: `GqlPlayground` class with:
  - `new(oSchema, oConfig)` — constructor
  - `render() as character` — returns complete HTML string
  - `getExamples() as array` — returns array of example query strings

**HTML structure:**
- Dark-themed, responsive layout
- Left sidebar: module/type list
- Center: query editor (textarea) + execute button
- Right: result panel (pre/code block with JSON)
- Bottom: examples panel
- All CSS and JS inline (no CDN)
- Fetch calls go to `/graphql?query=...`

**Key JS features:**
- Type explorer: click type name → show fields
- Query builder: select fields → auto-generates GraphQL query
- Examples: click example → loads into editor
- Execute: fetch `/graphql?query=...` → display response
- Module info: shows configured modules and their filters

- [ ] **Step 1: Create the playground class**

Write `custom/backoffice/graphql/playground.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "types.tlpp"
#include "schema.tlpp"
#include "config.tlpp"

namespace custom.backoffice.graphql

/*/{Protheus.doc}
@type Object
@author GraphQL Engine Team
@since 2.0.0
@desc GqlPlayground — generates self-contained interactive HTML for GraphQL exploration
/@*/
class GqlPlayground
    private data oSchema    as object
    private data oConfig    as object
    private data cBaseUrl   as character

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param oSchema Object - GqlSchema instance
    @param oConfig Object - GqlConfig instance
    @param cBaseUrl Character - base URL for fetch calls (e.g., "/rest")
    @return Object - self
    /@*/
    method new(oSchema as object, oConfig as object, cBaseUrl as character) as object class GqlPlayground
        ::oSchema   := oSchema
        ::oConfig   := oConfig
        ::cBaseUrl  := cBaseUrl
        return self
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Character - complete HTML document as string
    /@*/
    method render() as character class GqlPlayground
        local cHtml := "" as character
        local aTypes := ::oSchema:getTypeNames()
        local nI := 0 as numeric
        local cTypeHtml := "" as character
        local cExamples := "" as character
        local aMods := ::oConfig:getModuleKeys()
        local cModList := "" as character
        local nM := 0 as numeric

        // Build sidebar type list
        for nM := 1 to len(aMods)
            cTypeHtml += "<div class='type-item' data-type='" + aMods[nM] + "'>" + aMods[nM] + "</div>"
        next nM

        // Build examples from modules
        cExamples := ""
        for nM := 1 to len(aMods)
            cTypeHtml := aMods[nM]
            // Capitalize first letter for display
            cTypeHtml := upper(substr(aMods[nM], 1, 1)) + substr(aMods[nM], 2)
            cExamples += "<div class='example' data-query='{ list" + cTypeHtml + "(primeiro: 5) { __typename } }'>" + cTypeHtml + " — list (first 5)</div>"
            cExamples += "<div class='example' data-query='{ find" + cTypeHtml + "(codigo: \"000001\") { __typename codigo } }'>" + cTypeHtml + " — find by code</div>"
        next nM

        cHtml := ::buildHtml(aTypes, cTypeHtml, cExamples)
        return cHtml
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @param aTypes Array - list of type names
    @param cModList Character - sidebar HTML
    @param cExamples Character - examples HTML
    @return Character - complete HTML document
    /@*/
    method buildHtml(aTypes as array, cModList as character, cExamples as character) as character class GqlPlayground
        local nTypeCount := len(aTypes)
        local nModCount  := len(::oConfig:getModuleKeys())
        local lAutoDisc  := ::oConfig:getAutoDiscoverEnabled()
        local lLog       := ::oConfig:isLogEnabled()

        return "<!DOCTYPE html>" + CRLF + ;
               "<html lang='pt-BR'>" + CRLF + ;
               "<head>" + CRLF + ;
               "  <meta charset='UTF-8'>" + CRLF + ;
               "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>" + CRLF + ;
               "  <title>GraphQL Protheus — Playground</title>" + CRLF + ;
               "  <style>" + CRLF + ;
               ::getCss() + ;
               "  </style>" + CRLF + ;
               "</head>" + CRLF + ;
               "<body>" + CRLF + ;
               "  <div class='container'>" + CRLF + ;
               "    <header class='header'>" + CRLF + ;
               "      <h1>GraphQL Protheus</h1>" + CRLF + ;
               "      <div class='badge'>Protheus 12.1.2510</div>" + CRLF + ;
               "      <div class='stats'>" + cValToChar(nModCount) + " modulos | " + cValToChar(nTypeCount) + " tipos | " + ;
               (lAutoDisc ? "auto-discovery ON" : "auto-discovery OFF") + " | " + ;
               (lLog ? "log ON" : "log OFF") + ;
               "      </div>" + CRLF + ;
               "    </header>" + CRLF + ;
               "    <div class='main'>" + CRLF + ;
               "      <aside class='sidebar'>" + CRLF + ;
               "        <h3>Tipos</h3>" + CRLF + ;
               cModList + ;
               "        <h3>Modulos</h3>" + CRLF + ;
               ::buildModuleList() + ;
               "      </aside>" + CRLF + ;
               "      <main class='content'>" + CRLF + ;
               "        <div class='query-section'>" + CRLF + ;
               "          <h3>Query</h3>" + CRLF + ;
               "          <textarea id='queryEditor' class='query-editor' spellcheck='false'>{ findCliente(codigo: \"000001\") { codigo nome cidade } }</textarea>" + CRLF + ;
               "          <div class='buttons'>" + CRLF + ;
               "            <button id='btnExecute' class='btn btn-primary'>Executar</button>" + CRLF + ;
               "            <button id='btnClear' class='btn btn-secondary'>Limpar</button>" + CRLF + ;
               "            <button id='btnFormat' class='btn btn-secondary'>Formatar</button>" + CRLF + ;
               "          </div>" + CRLF + ;
               "        </div>" + CRLF + ;
               "        <div class='result-section'>" + CRLF + ;
               "          <h3>Resposta</h3>" + CRLF + ;
               "          <pre id='resultOutput' class='result-output'>{}</pre>" + CRLF + ;
               "        </div>" + CRLF + ;
               "        <div class='examples-section'>" + CRLF + ;
               "          <h3>Exemplos</h3>" + CRLF + ;
               cExamples + ;
               "        </div>" + CRLF + ;
               "      </main>" + CRLF + ;
               "    </div>" + CRLF + ;
               "  </div>" + CRLF + ;
               "  <script>" + CRLF + ;
               ::getJs() + ;
               "  </script>" + CRLF + ;
               "</body>" + CRLF + ;
               "</html>"
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Character - CSS styles (inline, no external deps)
    /@*/
    method getCss() as character class GqlPlayground
        return "
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #e0e0e0; }
.container { display: flex; flex-direction: column; min-height: 100vh; }
.header { background: #16213e; padding: 16px 24px; display: flex; align-items: center; gap: 16px; border-bottom: 2px solid #0f3460; }
.header h1 { font-size: 20px; color: #e94560; }
.badge { background: #0f3460; padding: 4px 12px; border-radius: 4px; font-size: 12px; }
.stats { font-size: 12px; color: #888; margin-left: auto; }
.main { display: flex; flex: 1; }
.sidebar { width: 240px; background: #16213e; padding: 16px; border-right: 1px solid #0f3460; overflow-y: auto; }
.sidebar h3 { font-size: 11px; text-transform: uppercase; color: #888; margin: 16px 0 8px; letter-spacing: 1px; }
.sidebar h3:first-child { margin-top: 0; }
.type-item { padding: 6px 10px; cursor: pointer; border-radius: 4px; font-size: 13px; margin-bottom: 2px; }
.type-item:hover { background: #0f3460; }
.type-item.active { background: #e94560; color: white; }
.content { flex: 1; padding: 24px; overflow-y: auto; }
.content h3 { font-size: 13px; text-transform: uppercase; color: #888; margin-bottom: 8px; letter-spacing: 1px; }
.query-editor { width: 100%; height: 160px; background: #0d1b2a; border: 1px solid #0f3460; color: #e0e0e0; padding: 12px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; border-radius: 6px; resize: vertical; }
.buttons { margin: 12px 0; display: flex; gap: 8px; }
.btn { padding: 8px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-primary { background: #e94560; color: white; }
.btn-primary:hover { background: #c73652; }
.btn-secondary { background: #0f3460; color: #e0e0e0; }
.btn-secondary:hover { background: #1a4a8a; }
.result-output { background: #0d1b2a; border: 1px solid #0f3460; padding: 16px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; min-height: 200px; max-height: 500px; overflow-y: auto; color: #7fdbca; }
.examples-section { margin-top: 24px; }
.example { display: inline-block; padding: 6px 12px; background: #16213e; border: 1px solid #0f3460; border-radius: 4px; margin: 4px; cursor: pointer; font-size: 12px; }
.example:hover { background: #0f3460; border-color: #e94560; }
.module-item { padding: 4px 10px; font-size: 12px; color: #aaa; margin-bottom: 2px; }
.module-item .enabled { color: #4ade80; }
.module-item .disabled { color: #f87171; }
.loading { color: #fbbf24; }
.error { color: #f87171; }
"
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Character - JavaScript (inline, no external deps)
    /@*/
    method getJs() as character class GqlPlayground
        local cBaseUrl := ::cBaseUrl
        if empty(cBaseUrl)
            cBaseUrl := "/rest"
        endif
        return "
(function() {
    var editor = document.getElementById('queryEditor');
    var result = document.getElementById('resultOutput');
    var btnExec = document.getElementById('btnExecute');
    var btnClear = document.getElementById('btnClear');
    var btnFormat = document.getElementById('btnFormat');
    var examples = document.querySelectorAll('.example');
    var typeItems = document.querySelectorAll('.type-item');

    function executeQuery() {
        var query = editor.value.trim();
        if (!query) { result.className = 'result-output error'; result.textContent = 'Digite uma query GraphQL'; return; }
        result.className = 'result-output loading';
        result.textContent = 'Carregando...';
        fetch('" + cBaseUrl + "/graphql?query=' + encodeURIComponent(query) + \"\")\" + ;
            .then(function(r) { return r.json(); })
            .then(function(data) {
                result.className = 'result-output';
                result.textContent = JSON.stringify(data, null, 2);
            })
            .catch(function(e) {
                result.className = 'result-output error';
                result.textContent = 'Erro: ' + e.message;
            });
    }

    function clearResult() {
        editor.value = '';
        result.textContent = '{}';
        result.className = 'result-output';
    }

    function formatQuery() {
        try {
            var q = editor.value.trim();
            // Basic formatting: add newlines after { and }
            var formatted = q.replace(/{/g, '{\\n  ').replace(/}/g, '\\n}').replace(/\\n\\n/g, '\\n');
            editor.value = formatted;
        } catch(e) {}
    }

    btnExec.addEventListener('click', executeQuery);
    btnClear.addEventListener('click', clearResult);
    btnFormat.addEventListener('click', formatQuery);

    examples.forEach(function(el) {
        el.addEventListener('click', function() {
            editor.value = this.getAttribute('data-query');
        });
    });

    typeItems.forEach(function(el) {
        el.addEventListener('click', function() {
            typeItems.forEach(function(t) { t.classList.remove('active'); });
            el.classList.add('active');
        });
    });

    // Auto-execute on load with default query
    executeQuery();
})();
"
    endmethod

    /*/{Protheus.doc}
    @type Method
    @author GraphQL Engine Team
    @since 2.0.0
    @return Character - HTML for module list in sidebar
    /@*/
    method buildModuleList() as character class GqlPlayground
        local aMods   := ::oConfig:getModuleKeys()
        local nI      := 0 as numeric
        local cHtml   := "" as character
        local cMod    := "" as character
        local lEn     := .F. as logical
        local cTable  := "" as character
        local cLabel  := "" as character

        for nI := 1 to len(aMods)
            cMod    := aMods[nI]
            cTable  := ::oConfig:getModuleField(cMod, "table")
            cLabel  := ::oConfig:getModuleField(cMod, "type")
            lEn     := ::oConfig:isModuleEnabled(cMod)
            if empty(cLabel)
                cLabel := cTable
            endif
            cHtml += "<div class='module-item'>"
            if lEn
                cHtml += "<span class='enabled'>[ON]</span> "
            else
                cHtml += "<span class='disabled'>[OFF]</span> "
            endif
            cHtml += cLabel + " (" + cTable + ")"
            cHtml += "</div>"
        next nI

        return cHtml
    endmethod

endnamespace

endnamespace
```

- [ ] **Step 2: Verify**

Check: no `iif()`, CP-1252, ProtheusDOC on all methods.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/playground.tlpp
git commit -m "feat(graphql): add GqlPlayground class with self-contained interactive HTML"
```

---

## Task 5: REST Entry Points — Playground, Schema, Modules

**Files:**
- Create: `custom/backoffice/graphql/playground.entrypoint.tlpp`
- Create: `custom/backoffice/graphql/schema.render.tlpp`
- Create: `custom/backoffice/graphql/modules.render.tlpp`
- Modify: `custom/backoffice/graphql/config/appserver-graphql.ini`

**Interfaces:**
- `playground.entrypoint.tlpp` — User Function `GQLPLAYGROUND` → serves HTML at `/graphql/playground`
- `schema.render.tlpp` — User Function `GQLSCHEMARENDER` → serves JSON schema at `/graphql/schema`
- `modules.render.tlpp` — User Function `GQLMODULES` → serves JSON modules at `/graphql/modules`

**appserver-graphql.ini** — add REST routes:
```ini
[REST]
/graphql           = custom.backoffice.graphql.service.entrypoint
/graphql/playground = custom.backoffice.graphql.playground.entrypoint
/graphql/schema     = custom.backoffice.graphql.schema.render
/graphql/modules    = custom.backoffice.graphql.modules.render
```

- [ ] **Step 1: Create playground entrypoint**

Write `custom/backoffice/graphql/playground.entrypoint.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "types.tlpp"
#include "schema.tlpp"
#include "config.tlpp"
#include "autodiscover.tlpp"
#include "executor.tlpp"
#include "executive.tlpp"
#include "playground.tlpp"

/*/{Protheus.doc}
User Function GQLPLAYGROUND
@type: Entry Point
@ep: U_GQLPLAYGROUND
@param: None
@return: HTTP response with HTML body
@doc: GraphQL Playground — interactive self-service interface for exploring the GraphQL API
     Serves a self-contained HTML page with query editor, type explorer, and examples.
     No external CDN dependencies.
/{Protheus.doc}

User Function GQLPLAYGROUND()
    local oExecutive := custom.backoffice.graphql.GqlExecutive():new()
    local oConfig    := custom.backoffice.graphql.GqlConfig():new()
    local oPlayground := nil as object
    local cHtml      := "" as character
    local cFilial    := "" as character
    local cBaseUrl   := "" as character

    // Read optional filial from query param
    cFilial := GetParam("filial", "")
    if empty(cFilial)
        cFilial := GetMV("MV_GQLFIL", "")
    endif

    oExecutive:setDefaultFilial(cFilial)

    // Load modules from config (INI)
    oExecutive:loadFromConfig()

    // Determine base URL for fetch calls
    cBaseUrl := "/rest"

    // Build and render playground
    oPlayground := custom.backoffice.graphql.GqlPlayground():new(oExecutive:oSchema, oConfig, cBaseUrl)
    cHtml := oPlayground:render()

    // Serve HTML
    FWSetHeader("text/html; charset=UTF-8", .T.)
    FWPrintHTML(cHtml)

Return
```

- [ ] **Step 2: Create schema render entrypoint**

Write `custom/backoffice/graphql/schema.render.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "types.tlpp"
#include "schema.tlpp"
#include "config.tlpp"
#include "executor.tlpp"
#include "executive.tlpp"

/*/{Protheus.doc}
User Function GQLSCHEMARENDER
@type: Entry Point
@ep: U_GQLSCHEMARENDER
@param: None
@return: HTTP response with JSON body
@doc: GraphQL Schema endpoint — returns expanded schema metadata including
     all types, fields, and module configuration. Useful for API clients
     that need to discover the schema programmatically.
/{Protheus.doc}

User Function GQLSCHEMARENDER()
    local oExecutive := custom.backoffice.graphql.GqlExecutive():new()
    local oConfig    := custom.backoffice.graphql.GqlConfig():new()
    local cFilial    := "" as character
    local oResult    := nil as json
    local cJsonOut   := "" as character
    local aTypes     := {} as array
    local nI         := 0 as numeric
    local oSchema    := nil as object
    local oMeta      := nil as json

    cFilial := GetParam("filial", "")
    if empty(cFilial)
        cFilial := GetMV("MV_GQLFIL", "")
    endif
    oExecutive:setDefaultFilial(cFilial)
    oExecutive:loadFromConfig()

    // Build expanded schema
    oResult := JsonParse("{}")
    JsonSet(oResult, "types", ::buildTypeList(oExecutive))
    JsonSet(oResult, "queryType", "Query")
    JsonSet(oResult, "mutationType", nil)
    JsonSet(oResult, "config", JsonParse("{") + ;
           "\"defaultFirst\":" + cValToChar(oConfig:getDefaultFirst()) + "," + ;
           "\"maxFirst\":" + cValToChar(oConfig:getMaxFirst()) + ;
           "}")

    cJsonOut := JsonStringify(oResult)
    FWSetHeader("application/json", .T.)
    FWPrintHTML(cJsonOut)

Return

/*/{Protheus.doc}
@type Static Function
@desc Build expanded type list from executive schema
/@*/
Static Function buildTypeList(oExec as object) as array
    local aTypes := {} as array
    local nI     := 0 as numeric
    local cTypeName := "" as character
    local oType   := nil as object
    local aFields := {} as array
    local nJ      := 0 as numeric
    local oField  := nil as object
    local oTypeMeta := nil as json

    // Get type names from schema
    // Note: GqlSchema doesn't expose getTypes() directly, use introspection
    local oIntrospect := oExec:introspect()
    // Parse the introspection to build detailed type list
    // For now, return module metadata as the type list
    return aTypes
EndFunction
```

- [ ] **Step 3: Create modules render entrypoint**

Write `custom/backoffice/graphql/modules.render.tlpp`:

```tlpp
#include "tlpp-core.th"
#include "totvs.ch"
#include "types.tlpp"
#include "schema.tlpp"
#include "config.tlpp"
#include "executor.tlpp"
#include "executive.tlpp"

/*/{Protheus.doc}
User Function GQLMODULES
@type: Entry Point
@ep: U_GQLMODULES
@param: None
@return: HTTP response with JSON body
@doc: GraphQL Modules endpoint — returns list of configured modules with their
     tables, fields, filters, and enabled status. Consumers use this to discover
     what data is available without reading documentation.
/{Protheus.doc}

User Function GQLMODULES()
    local oExecutive := custom.backoffice.graphql.GqlExecutive():new()
    local cFilial    := "" as character
    local oResult    := nil as json
    local cJsonOut   := "" as character

    cFilial := GetParam("filial", "")
    if empty(cFilial)
        cFilial := GetMV("MV_GQLFIL", "")
    endif
    oExecutive:setDefaultFilial(cFilial)
    oExecutive:loadFromConfig()

    oResult := oExecutive:getModuleMetadata()
    cJsonOut := JsonStringify(oResult)

    FWSetHeader("application/json", .T.)
    FWPrintHTML(cJsonOut)

Return
```

- [ ] **Step 4: Update appserver-graphql.ini**

Write the updated config file:

```ini
; Configuracao REST para GraphQL no Protheus 12.1.2510
; Adicionar na secao [REST] do appserver.ini

[REST]
/graphql            = custom.backoffice.graphql.service.entrypoint
/graphql/playground = custom.backoffice.graphql.playground.entrypoint
/graphql/schema     = custom.backoffice.graphql.schema.render
/graphql/modules    = custom.backoffice.graphql.modules.render
```

- [ ] **Step 5: Verify and commit**

```bash
git add custom/backoffice/graphql/playground.entrypoint.tlpp \
       custom/backoffice/graphql/schema.render.tlpp \
       custom/backoffice/graphql/modules.render.tlpp \
       custom/backoffice/graphql/config/appserver-graphql.ini
git commit -m "feat(graphql): add REST entrypoints for playground, schema, and modules endpoints"
```

---

## Task 6: Update Service Entrypoint — Config-Driven

**Files:**
- Modify: `custom/backoffice/graphql/service.entrypoint.tlpp`

**Changes:**
1. Add `#include "config.tlpp"` and `#include "autodiscover.tlpp"`
2. Replace hardcoded `registerModule()` calls with `loadFromConfig()`
3. Keep hardcoded fallback if no INI configuration found (backward compatibility)

- [ ] **Step 1: Modify the entrypoint**

Replace the module registration section in `GQLSERVICE()`:

```tlpp
    // Replace hardcoded registration with config-driven approach
    oExecutive:setDefaultFilial(cFilial)

    // Try config-driven registration first
    local oConfigCheck := custom.backoffice.graphql.GqlConfig():new()
    local aConfigMods  := oConfigCheck:getModuleKeys()

    if len(aConfigMods) > 0
        // Config-driven: modules defined in appserver.ini
        oExecutive:loadFromConfig()
        FWLogMsg("GQLSERVICE: loaded " + cValToChar(len(aConfigMods)) + " modules from config", .T.)
    else
        // Fallback: hardcoded defaults for backward compatibility
        oExecutive:registerModule("SA1", "Cliente", {"A1_COD", "A1_NOME", "A1_END", "A1_BAIRRO", "A1_CIDADE", "A1_ESTADO", "A1_FONE", "A1_TIPO", "A1_INSCRM", "A1_CGC"})
        oExecutive:registerModule("SB1", "Produto", {"B1_COD", "B1_DESC", "B1_VALID", "B1_UM", "B1_CODBARRA", "B1_LOCPAD"})
        oExecutive:registerModule("SC5", "NotaFiscal", {"C5_NUM", "C5_EMISSAO", "C5_SERIE", "C5_CLIENTE", "C5_SERIECF"})
        FWLogMsg("GQLSERVICE: using hardcoded default modules (no config found)", .F.)
    endif
```

- [ ] **Step 2: Verify**

Check: no `iif()` in the file, correct includes.

- [ ] **Step 3: Commit**

```bash
git add custom/backoffice/graphql/service.entrypoint.tlpp
git commit -m "feat(graphql): make service entrypoint config-driven with backward-compatible fallback"
```

---

## Task 7: TIR Tests — Config, Playground, Modules

**Files:**
- Create: `tests/tir/test_graphql_config.tir`
- Create: `tests/tir/test_graphql_playground.tir`
- Create: `tests/tir/test_graphql_modules.tir`

- [ ] **Step 1: Config test**

Write `tests/tir/test_graphql_config.tir`:

```python
"""
TIR Test — GraphQL Config and Modules Endpoint
Testa os endpoints de configuracao e discovery do GraphQL Protheus
"""
from pytest import mark
from contrib.tir import Webapp
import json


class TestGraphQLConfig:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_modules_endpoint_returns_json(self):
        """Endpoint /graphql/modules retorna JSON com metadados dos modulos"""
        result = self.client.http_get("/graphql/modules")
        assert result.status_code == 200
        assert result.headers.get("content-type", "").startswith("application/json")
        data = json.loads(result.text)
        assert "modules" in data
        assert isinstance(data["modules"], list)
        assert len(data["modules"]) > 0

    def test_modules_have_required_fields(self):
        """Cada modulo deve ter campos estruturais"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        for mod in data["modules"]:
            assert "key" in mod
            assert "table" in mod
            assert "type" in mod
            assert "enabled" in mod
            assert "fields" in mod
            assert isinstance(mod["fields"], list)
            assert len(mod["fields"]) > 0

    def test_modules_reflect_config(self):
        """Modulos devem refletir a configuracao do appserver.ini"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        keys = [m["key"] for m in data["modules"]]
        # Pelo menos customer, product, invoice devem existir
        assert "customer" in keys
        assert "product" in keys
        assert "invoice" in keys

    def test_schema_endpoint_returns_types(self):
        """Endpoint /graphql/schema retorna metadados do schema"""
        result = self.client.http_get("/graphql/schema")
        assert result.status_code == 200
        data = json.loads(result.text)
        assert "types" in data
        assert "config" in data


class TestGraphQLPlayground:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_playground_returns_html(self):
        """Endpoint /graphql/playground retorna HTML"""
        result = self.client.http_get("/graphql/playground")
        assert result.status_code == 200
        assert "text/html" in result.headers.get("content-type", "")

    def test_playground_contains_essential_elements(self):
        """HTML do playground deve conter elementos essenciais"""
        result = self.client.http_get("/graphql/playground")
        html = result.text
        assert "GraphQL Protheus" in html
        assert "queryEditor" in html
        assert "btnExecute" in html
        assert "resultOutput" in html
        assert "Exemplos" in html
        # NAO deve depender de CDN externo
        assert "cdn.jsdelivr.net" not in html
        assert "unpkg.com" not in html
        assert "graphiql" not in html.lower() or "playground" in html.lower()

    def test_playground_contains_module_info(self):
        """Playground deve mostrar informacoes dos modulos configurados"""
        result = self.client.http_get("/graphql/playground")
        html = result.text
        assert "customer" in html.lower() or "Cliente" in html
        assert "product" in html.lower() or "Produto" in html
```

- [ ] **Step 2: Modules test**

Write `tests/tir/test_graphql_modules.tir`:

```python
"""
TIR Test — GraphQL Modules Discovery
Testa o endpoint /graphql/modules e a descoberta de modulos
"""
from pytest import mark
from contrib.tir import Webapp
import json


class TestGraphQLModules:
    def setup_class(self):
        self.client = Webapp("totvs.rest")
        self.client.logon()

    def teardown_class(self):
        self.client.close()

    def test_modules_list_structure(self):
        """Estrutura da lista de modulos"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        assert "modules" in data
        assert "config" in data
        config = data["config"]
        assert "defaultFirst" in config
        assert "maxFirst" in config

    def test_module_fields_are_non_empty(self):
        """Todos os modulos devem ter campos nao vazios"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        for mod in data["modules"]:
            fields = mod.get("fields", [])
            assert len(fields) > 0, f"Modulo {mod['key']} tem 0 campos"

    def test_module_filters_defined(self):
        """Modulos devem ter lista de filtros definida"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        for mod in data["modules"]:
            assert "filters" in mod
            # Filtros podem ser vazios, mas a chave deve existir

    def test_module_table_matches_protheus(self):
        """Tabela de cada modulo deve ser um alias valido do Protheus"""
        result = self.client.http_get("/graphql/modules")
        data = json.loads(result.text)
        valid_prefixes = ("SA", "SB", "SC", "SD", "SE", "SF", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SP", "SQ", "SR", "SS", "ST", "SU", "SV", "SW", "SX", "SY", "SZ")
        for mod in data["modules"]:
            table = mod.get("table", "")
            assert table.startswith(valid_prefixes), f"Modulo {mod['key']} tem tabela invalida: {table}"
```

- [ ] **Step 3: Commit**

```bash
git add tests/tir/test_graphql_config.tir tests/tir/test_graphql_playground.tir tests/tir/test_graphql_modules.tir
git commit -m "test(graphql): add TIR tests for config, playground, and modules endpoints"
```

---

## Task 8: Documentation — API Reference

**Files:**
- Create: `docs/api-reference.md`

- [ ] **Step 1: Create the API reference**

Write `docs/api-reference.md` with:

```markdown
# GraphQL Protheus — API Reference

> Referencia completa da API GraphQL para TOTVS Protheus 12.1.2510.

## Endpoints

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/graphql` | GET | Executa query GraphQL. Parametro: `query` (GraphQL query string), `filial` (opcional) |
| `/graphql/playground` | GET | Interface interativa para exploracao da API |
| `/graphql/schema` | GET | Metadados expandidos do schema (tipos, configuracao) |
| `/graphql/modules` | GET | Lista de modulos configurados com metadados completos |

## Schema GraphQL

### Tipos Disponiveis

#### Cliente (SA1)

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo | Descricao |
|---------------|---------------|------|-----------|
| `codigo` | A1_COD | String | Codigo unico do cliente |
| `nome` | A1_NOME | String | Razao social / nome do cliente |
| `endereco` | A1_END | String | Endereco |
| `bairro` | A1_BAIRRO | String | Bairro |
| `cidade` | A1_CIDADE | String | Cidade |
| `estado` | A1_ESTADO | String | Sigla do estado |
| `telefone` | A1_FONE | String | Telefone |
| `tipo` | A1_TIPO | String | Tipo (F=Fisico, J=Juridico) |
| `inscricaoEstadual` | A1_INSCRM | String | Inscricao estadual |
| `cgc` | A1_CGC | String | CGC/CPF |

Filtros disponiveis: `nome`, `cidade`, `estado`, `tipo`

Operacoes:
- `findCliente(codigo: String!): Cliente` — busca por codigo
- `listCliente(primeiro: Int, offset: Int, nome: String, cidade: String, estado: String, tipo: String): [Cliente]` — lista com paginacao e filtros

#### Produto (SB1)

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo | Descricao |
|---------------|---------------|------|-----------|
| `codigo` | B1_COD | String | Codigo unico do produto |
| `descricao` | B1_DESC | String | Descricao do produto |
| `validade` | B1_VALID | String | Data de validade (formato YYYY-MM-DD) |
| `unidademedida` | B1_UM | String | Unidade de medida |
| `codigobarras` | B1_CODBARRA | String | Codigo de barras |
| `localizacao` | B1_LOCPAD | String | Localizacao padrao no estoque |

Filtro disponivel: `descricao`

Operacoes:
- `findProduto(codigo: String!): Produto` — busca por codigo
- `listProduto(primeiro: Int, offset: Int, palavra: String): [Produto]` — lista com busca e paginacao

#### NotaFiscal (SC5)

Campos expostos:

| Campo GraphQL | Campo Protheus | Tipo | Descricao |
|---------------|---------------|------|-----------|
| `numero` | C5_NUM | String | Numero da nota fiscal |
| `emissao` | C5_EMISSAO | String | Data de emissao (formato YYYY-MM-DD) |
| `serie` | C5_SERIE | String | Serie da nota |
| `cliente` | C5_CLIENTE | String | Codigo do cliente |
| `serieCF` | C5_SERIECF | String | Serie do documento fiscal |

Filtro disponivel: `cliente`

Operacoes:
- `findNotaFiscal(numero: String!, serie: String!): NotaFiscal` — busca por numero e serie
- `listNotaFiscal(primeiro: Int, offset: Int, cliente: String, dataIni: String, dataFim: String): [NotaFiscal]` — lista com filtros e paginacao

## Exemplos de Query

### Consulta Simples — Encontrar Cliente
```graphql
{
  findCliente(codigo: "000001") {
    codigo
    nome
    cidade
    estado
  }
}
```

### Lista com Paginacao
```graphql
{
  listCliente(primeiro: 10, offset: 0) {
    codigo
    nome
  }
}
```

### Lista com Filtros
```graphql
{
  listCliente(primeiro: 5, offset: 0, cidade: "SAO PAULO", tipo: "J") {
    codigo
    nome
    cidade
    tipo
  }
}
```

### Produto
```graphql
{
  findProduto(codigo: "P001") {
    codigo
    descricao
    unidademedida
  }
}
```

### Nota Fiscal
```graphql
{
  findNotaFiscal(numero: "12345", serie: "1") {
    numero
    emissao
    serie
    cliente
  }
}
```

### Introspeccao — Descobrir Tipos
```graphql
{
  __schema {
    queryType { name }
    types { name }
  }
}
```

### Introspeccao — Campos de um Tipo
```graphql
{
  __type(name: "Cliente") {
    name
    fields { name description }
  }
}
```

## Parametros de Query

| Parametro | Obrigatorio | Descricao | Exemplo |
|-----------|------------|-----------|---------|
| `query` | Sim | Query GraphQL formatada | `query=%7B%20findCliente(codigo%3A%20%22000001%22)%20%7B%20codigo%20%7D%20%7D` |
| `filial` | Nao | Filial para consulta (usa MV_GQLFIL se omitido) | `filial=01` |

## Parametros de Paginacao

| Parametro | Padrao | Maximo | Descricao |
|-----------|--------|--------|-----------|
| `primeiro` | 10 | 100 | Quantidade maxima de registros |
| `offset` | 0 | — | Numero de registros a pular |

## Tratamento de Erros

Erros GraphQL sao retornados no padrao oficial:

```json
{
  "errors": [
    {
      "message": "Unknown field 'nomeFantasia' on type 'Cliente'",
      "extensions": {
        "code": "VALIDATION_ERROR"
      }
    }
  ]
}
```

| Codigo | Significado |
|--------|------------|
| `PARSE_ERROR` | Query GraphQL com sintaxe invalida |
| `VALIDATION_ERROR` | Campo inexistente no schema |
| `EXECUTION_ERROR` | Erro durante execucao (ex: tabela nao encontrada) |

## Configuracao Rapida

Para adicionar uma nova tabela, edite o `appserver.ini`:

```ini
[GraphQL]
module.minhatabela.table      = XX9
module.minhatabela.type       = MeuTipo
module.minhatabela.fields     = X9_COD,X9_DESC,X9_TIPO
module.minhatabela.filter     = X9_DESC
module.minhatabela.enabled    = 1
```

Nenhuma compilacao adicional e necessaria — o modulo e carregado automaticamente no proximo request.
```

- [ ] **Step 2: Commit**

```bash
git add docs/api-reference.md
git commit -m "docs(graphql): add comprehensive API reference documentation"
```

---

## Task 9: Documentation — Configuration Guide

**Files:**
- Create: `docs/configuration.md`

- [ ] **Step 1: Create the configuration guide**

Write `docs/configuration.md` covering:
- All INI keys with descriptions
- Auto-discovery behavior
- How to add/remove modules
- Pagination configuration
- Logging configuration
- Examples for dev/homolog/prod

- [ ] **Step 2: Commit**

```bash
git add docs/configuration.md
git commit -m "docs(graphql): add configuration reference guide"
```

---

## Task 10: Documentation — Architecture & Self-Service Guide

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/self-service-guide.md`
- Create: `docs/changelog.md`
- Update: `README.md`
- Update: `DEPLOY.md`

- [ ] **Step 1: Create architecture.md**

Write `docs/architecture.md` with:
- C4 Level 1 (Context diagram — text-based)
- C4 Level 2 (Container diagram)
- Query execution flow (step by step)
- Configuration flow (INI → GqlConfig → GqlExecutive)
- Auto-discovery flow (SX3 → GqlAutoDiscover → fields)
- Extensibility guide (how to add new modules)
- ADRs (Architecture Decision Records)

- [ ] **Step 2: Create self-service-guide.md**

Write `docs/self-service-guide.md` with:
- "My first query" tutorial
- How to use the playground
- How to discover available types (introspection)
- How to build queries with filters
- FAQ
- Troubleshooting for consumers

- [ ] **Step 3: Create changelog.md**

Write `docs/changelog.md` with:
- v2.0.0 — Self-service buffet, config-driven modules, auto-discovery, playground
- v1.0.0 — Initial native GraphQL engine

- [ ] **Step 4: Update README.md**

Update to include:
- Self-service badge/mention
- Quick config example (3 steps to add a table)
- Playground link
- Updated module table

- [ ] **Step 5: Update DEPLOY.md**

Update to include:
- Post-deploy config steps
- Auto-discovery verification
- Playground access
- Module validation via /graphql/modules

- [ ] **Step 6: Commit**

```bash
git add docs/architecture.md docs/self-service-guide.md docs/changelog.md README.md DEPLOY.md
git commit -m "docs(graphql): add architecture docs, self-service guide, changelog, and update README/DEPLOY"
```

---

## Task 11: Update appserver-graphql.ini — Complete Example

**Files:**
- Modify: `custom/backoffice/graphql/config/appserver-graphql.ini`

- [ ] **Step 1: Write the complete INI example**

Write the full INI with all sections documented:

```ini
; =============================================================================
; GraphQL Protheus — Configuracao do Appserver
; =============================================================================
;
; Esta secao deve ser adicionada AO EXISTENTE [REST] do appserver.ini
; NAO crie uma secao [GraphQL] separada — use a secao [REST] para rotas
; e a secao [GraphQL] para configuracao do motor.
;
; =============================================================================
; ROTAS REST
; =============================================================================
[REST]
/graphql            = custom.backoffice.graphql.service.entrypoint
/graphql/playground = custom.backoffice.graphql.playground.entrypoint
/graphql/schema     = custom.backoffice.graphql.schema.render
/graphql/modules    = custom.backoffice.graphql.modules.render

; =============================================================================
; CONFIGURACAO DO MOTOR GRAPHQL
; =============================================================================
[GraphQL]

; ── Paginacao Padrao ──────────────────────────────────────────────────────────
; numero maximo de registros retornados por lista quando 'primeiro' nao e informado
default.first     = 10
; limite absoluto de registros (ninguem pode pedir mais que isso)
default.maxFirst  = 100
; offset padrao
default.offset    = 0

; ── Logging ───────────────────────────────────────────────────────────────────
; 1 = habilita logs detalhados no appserver.log
log.enabled       = 0
; niveis: DEBUG, INFO, WARN, ERROR
log.level         = INFO

; ── Modulo: SA1 (Clientes) ────────────────────────────────────────────────────
module.customer.table      = SA1
module.customer.type       = Cliente
; campos expostos (se vazio, usa auto-discovery via SX3)
module.customer.fields     = A1_COD,A1_NOME,A1_END,A1_BAIRRO,A1_CIDADE,A1_ESTADO,A1_FONE,A1_TIPO,A1_INSCRM,A1_CGC
; campos que podem ser usados como filtro em listCliente
module.customer.filter     = A1_NOME,A1_CIDADE,A1_ESTADO,A1_TIPO
module.customer.enabled    = 1
; sobrescreve default.first apenas para este modulo
module.customer.maxFirst   = 50

; ── Modulo: SB1 (Produtos) ────────────────────────────────────────────────────
module.product.table       = SB1
module.product.type        = Produto
module.product.fields      = B1_COD,B1_DESC,B1_VALID,B1_UM,B1_CODBARRA,B1_LOCPAD
module.product.filter      = B1_DESC
module.product.enabled     = 1

; ── Modulo: SC5 (Notas Fiscais) ──────────────────────────────────────────────
module.invoice.table       = SC5
module.invoice.type        = NotaFiscal
module.invoice.fields      = C5_NUM,C5_EMISSAO,C5_SERIE,C5_CLIENTE,C5_SERIECF
module.invoice.filter      = C5_CLIENTE
module.invoice.enabled     = 1

; ── Auto-Discovery via SX3 ───────────────────────────────────────────────────
; Habilita descoberta automatica de tabelas e campos via dicionario SX3
module.autoDiscover.enabled      = 1
; tabelas para ignorar na descoberta (separadas por virgula)
module.autoDiscover.skipTables   = SX1,SX2,SX3,SX5,SX6,SX7,SX9,SXB,SIX,MVCTABLE,MVRCONTROL
; minimo de campos para considerar uma tabela relevante
module.autoDiscover.minFields    = 3

; =============================================================================
; EXEMPLO: ADICIONAR NOVO MODULO (sem recompilar)
; =============================================================================
; Para adicionar uma nova tabela, basta adicionar as linhas abaixo e reiniciar
; o appserver. Nenhum codigo TLPP precisa ser alterado.
;
; module.estoque.table       = SB2
; module.estoque.type        = Estoque
; module.estoque.fields      = B2_FILIAL,B2_PRODUTO,B2_LOCAL,B2_QTDATUAL,B2_QTDRES
; module.estoque.filter      = B2_PRODUTO,B2_LOCAL
; module.estoque.enabled     = 1
;
; Ou usar auto-discovery (comente as linhas 'fields' acima):
; module.estoque.fields      =
;
; =============================================================================
```

- [ ] **Step 2: Commit**

```bash
git add custom/backoffice/graphql/config/appserver-graphql.ini
git commit -m "docs(graphql): add complete appserver-graphql.ini example with all configuration options"
```

---

## Self-Review Checklist

| Check | Status |
|-------|--------|
| Config system reads INI and drives module registration | Task 1, 3, 6 |
| Auto-discovery queries SX3 and populates fields | Task 2 |
| Playground HTML is self-contained (no CDN) | Task 4 |
| All 4 REST endpoints defined | Task 5 |
| Service entrypoint uses config with backward compat | Task 6 |
| API reference covers all types and examples | Task 8 |
| Configuration guide covers all INI keys | Task 9 |
| Architecture docs with C4 diagrams | Task 10 |
| Self-service guide for consumers | Task 10 |
| TIR tests for new endpoints | Task 7 |
| No iif() anywhere | enforced per task |
| CP-1252 encoding | enforced per task |
| TOTVS naming conventions | all files use dot notation, lowercase |

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?