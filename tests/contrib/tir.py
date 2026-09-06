# -*- coding: utf-8 -*-
"""TIR Webapp minimal REST harness.

Migrado do framework TOTVS TIR (browser/Selenium) para um cliente REST leve,
apenas para executar os testes de integracao do servico GraphQL Protheus.
A base URL padrao aponta para o HTTPREST do container `protheus-graphql`
(porta 9996, URL /rest). Pode ser sobrescrita via env PROTHEUS_REST_BASE.

Contrato usado pelos testes em tests/tir/:
    client = Webapp("totvs.rest")
    client.logon()
    result = client.http_get("/graphql?type=SA1")
    result.status_code, result.text, result.headers.get("content-type")
    client.close()
"""

import os
import json
import urllib.request
import urllib.error


DEFAULT_BASE_URL = os.environ.get(
    "PROTHEUS_REST_BASE",
    "http://localhost:9996/rest",
)

DEFAULT_TIMEOUT = int(os.environ.get("PROTHEUS_REST_TIMEOUT", "45"))


class HttpResponse:
    """Resposta HTTP com a superficie usada pelos testes (.status_code, .text, .headers)."""

    def __init__(self, status, text, headers, url):
        self.status_code = status
        self.text = text
        self.headers = headers
        self.url = url

    def json(self):
        return json.loads(self.text)


class Webapp:
    """Cliente REST para o endpoint GraphQL Protheus (substituto do tir.Webapp)."""

    def __init__(self, config_key="totvs.rest", base_url=None):
        self.config_key = config_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = DEFAULT_TIMEOUT

    def logon(self):
        # Security=0 no HTTPREST de teste: nao ha autenticacao.
        return True

    def close(self):
        return True

    def http_get(self, path, **kwargs):
        url = self.base_url + path if not path.startswith("http") else path
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                headers = {k: v for k, v in resp.headers.items()}
                return HttpResponse(resp.status, body, headers, url)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            headers = {k: v for k, v in exc.headers.items()}
            return HttpResponse(exc.code, body, headers, url)
        except urllib.error.URLError as exc:
            return HttpResponse(0, json.dumps({"errors": [{"message": str(exc.reason)}]}), {}, url)