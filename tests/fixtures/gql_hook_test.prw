#include "totvs.ch"

/*/{Protheus.doc}
GQLHOOKUP
Test fixture for the Field Hooks sub-project - uppercases a string value.
Not part of the GraphQL engine itself; used only by tests/tir/test_graphql_fieldhook_*.tir.
@type User Function
@author GraphQL Engine Team
@since 3.3.0
@param cValor Character - raw value
@return Character - cValor in upper case
/*/
User Function U_HookUp(cValor)
Return upper(cValor)
