#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de PDF da documentação — template padrão JMPM Tecnologia.

Converte arquivos Markdown em HTML (com capa, sumário e conteúdo),
aplica o template em docs/pdf/template/style.css e gera PDF via WeasyPrint.

Uso:
    python3 docs/pdf/build_pdfs.py
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("pip install markdown weasyprint")

try:
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration
except ImportError:
    sys.exit("pip install weasyprint")

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
TEMPLATE = DOCS / "pdf" / "template"
ASSETS = TEMPLATE / "assets"
STYLE = (TEMPLATE / "style.css").read_text(encoding="utf-8")
LOGO = ASSETS / "jmpm-logo.png"

# ---------------------------------------------------------------------------
# Documentos a gerar. Cada item:
#   id            -> nome do arquivo de saída
#   title         -> título principal da capa
#   doc_type      -> rótulo do tipo de documento (ex.: "Documentação Técnica")
#   subtitle      -> subtítulo da capa
#   sources       -> lista de arquivos .md (em ordem) na pasta docs/
#   intro         -> parágrafo introdutório opcional, após o sumário
# ---------------------------------------------------------------------------
DOCUMENTS = [
    {
        "id": "documentacao-tecnica",
        "title": "Motor Core GraphQL",
        "doc_type": "Documentação Técnica",
        "subtitle": "Motor Core GraphQL para Protheus — arquitetura, "
                    "implementação, configuração e operação",
        "sources": ["architecture.md", "manual-implementacao.md"],
        "intro": (
            "Este documento consolida a documentação técnica do Motor Core "
            "GraphQL para Protheus: arquitetura interna do motor, pipeline "
            "de requisição, modelo de mutations e o passo a passo completo "
            "de implantação, configuração e operação em ambiente Protheus."
        ),
    },
    {
        "id": "manual-do-usuario",
        "title": "Motor Core GraphQL",
        "doc_type": "Manual do Usuário",
        "subtitle": "Guia de utilização da API GraphQL exposta pelo "
                    "Motor Core GraphQL para Protheus",
        "sources": ["como-comecar.md", "manual-utilizacao.md"],
        "intro": (
            "Este manual orienta usuários e desenvolvedores no uso do Motor "
            "Core GraphQL para Protheus: como colocar o serviço no ar, "
            "executar consultas, mutations e introspecção, e interpretar "
            "erros e limitações da API."
        ),
    },
    {
        "id": "arquitetura",
        "title": "Arquitetura",
        "doc_type": "Documentação Técnica",
        "subtitle": "Arquitetura interna do Motor Core GraphQL para Protheus",
        "sources": ["architecture.md"],
        "intro": "Arquitetura interna do motor, pipeline de requisição e "
                 "modelo de mutations.",
    },
    {
        "id": "como-comecar",
        "title": "Como Começar",
        "doc_type": "Guia Rápido",
        "subtitle": "Guia rápido para colocar o Motor Core GraphQL "
                    "para Protheus em funcionamento",
        "sources": ["como-comecar.md"],
        "intro": "Guia rápido de início: compilar, implantar e executar a "
                 "primeira consulta em poucos minutos.",
    },
    {
        "id": "configuracao",
        "title": "Configuração",
        "doc_type": "Documentação Técnica",
        "subtitle": "Referência do arquivo graphql-config.json",
        "sources": ["configuration.md"],
        "intro": "Referência completa do arquivo de configuração do motor.",
    },
    {
        "id": "manual-implementacao",
        "title": "Manual de Implementação",
        "doc_type": "Manual Técnico",
        "subtitle": "Instalação, configuração e operação do Motor Core "
                    "GraphQL em ambiente Protheus",
        "sources": ["manual-implementacao.md"],
        "intro": "Guia completo para quem vai instalar, configurar e operar "
                 "o motor GraphQL em um ambiente Protheus.",
    },
    {
        "id": "manual-utilizacao",
        "title": "Manual de Utilização",
        "doc_type": "Manual do Usuário",
        "subtitle": "Referência completa da API GraphQL exposta pelo motor",
        "sources": ["manual-utilizacao.md"],
        "intro": "Referência completa da API GraphQL: endpoint, introspecção, "
                 "consultas, filtros, mutations e erros.",
    },
]

VERSION = "3.1.0"
COMPANY = "JMPM Tecnologia"


# ---------------------------------------------------------------------------
# Conversão Markdown -> HTML
# ---------------------------------------------------------------------------
def md_to_html(source: Path) -> str:
    raw = source.read_text(encoding="utf-8")
    body = markdown.markdown(
        raw,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={
            "toc": {"permalink": False},
        },
    )
    # Melhorar atributos de id nos headers para TOC
    return body


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\u00e0-\u00ff]+", "-", text)
    text = text.strip("-")
    return text


def anchorize(html_body: str) -> str:
    """Adiciona id aos headers <h1..h4> baseado no texto (para TOC)."""
    def repl(m: re.Match) -> str:
        level = m.group(1)
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", "", inner)
        text = html.unescape(text).strip()
        anch = slugify(text)
        return f'<h{level} id="{anch}">{inner}</h{level}>'
    return re.sub(r"<h([1-4])>(.*?)</h\1>", repl, html_body, flags=re.S)


def extract_headings(html_body: str):
    """Extrai (level, texto, id) dos headers para gerar o sumário."""
    items = []
    for m in re.finditer(r"<h([1-4]) id=\"([^\"]+)\">(.*?)</h\1>",
                         html_body, flags=re.S):
        level = int(m.group(1))
        anch = m.group(2)
        text = re.sub(r"<[^>]+>", "", m.group(3))
        text = html.unescape(text).strip()
        items.append((level, text, anch))
    return items


def toc_html(items) -> str:
    """Gera o HTML do sumário a partir dos headings (níveis 1-2)."""
    out = []
    out.append('<div class="toc">')
    out.append('<h2>Sumário</h2>')
    out.append('<ul>')
    for level, text, anch in items:
        if level > 2:
            continue
        out.append(f'<li><a href="#{anch}">{html.escape(text)}</a></li>')
    out.append('</ul>')
    out.append('</div>')
    return "\n".join(out)


def cover_html(doc) -> str:
    parts = []
    parts.append('<div class="cover">')
    parts.append('<div class="cover-band"></div>')
    parts.append(
        f'<div class="cover-logo"><img src="{LOGO}" alt="JMPM Tecnologia"></div>'
    )
    parts.append('<div class="cover-brand">'
                 '<div class="name">JMPM Tecnologia</div>'
                 '<div class="tagline">Tecnologia &amp; Desenvolvimento</div>'
                 '</div>')
    parts.append('<div class="cover-title">')
    parts.append(f'<div class="doc-type">{html.escape(doc["doc_type"])}</div>')
    parts.append(f'<h1>{html.escape(doc["title"])}</h1>')
    parts.append(f'<div class="subtitle">{html.escape(doc["subtitle"])}</div>')
    parts.append('</div>')
    parts.append('<div class="cover-meta">')
    parts.append(f'<div>Versão <span class="version">{VERSION}</span></div>')
    parts.append(f'<div>{COMPANY}</div>')
    parts.append(f'<div>{__import__("datetime").date.today().strftime("%d/%m/%Y")}</div>')
    parts.append('</div>')
    parts.append('<div class="cover-footer-band"></div>')
    parts.append('</div>')
    return "\n".join(parts)


def build_document(doc) -> str:
    """Marca o <title> para o header @top-right (string-set) e monta o HTML."""
    body_parts = []
    body_parts.append(cover_html(doc))

    full_md = []
    for src in doc["sources"]:
        p = DOCS / src
        if not p.exists():
            sys.exit(f"Fonte não encontrada: {p}")
        full_md.append(md_to_html(p))

    # Junta os markdown de cada fonte e anchoriza
    joined = "\n".join(full_md)
    joined = anchorize(joined)
    headings = extract_headings(joined)

    # HTML do sumário + intro + conteúdo
    content = "\n".join(
        [
            toc_html(headings),
            '<div class="doc-content">',
        ]
    )
    if doc.get("intro"):
        content += f'<p class="doc-meta"><strong>{html.escape(doc["doc_type"])}</strong> &mdash; {html.escape(doc["intro"])}</p>'
    content += joined
    content += "</div>"

    page_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{html.escape(doc['title'])}</title>
<style>{STYLE}</style>
</head>
<body>
{body_parts[0]}
<div class="pagebody">
{content}
</div>
</body>
</html>"""
    return page_html


def set_doc_title(html_in: str, title: str) -> str:
    """Insere um título de documento no body para o string-set() do header."""
    css_title = title.replace("\\", "\\\\").replace('"', '\\"')
    marker = (
        f'<div style="string-set: doc-title &quot;{css_title}&quot;; '
        'display:none"></div>'
    )
    return html_in.replace("<body>", f"<body>\n{marker}")


def render(doc, out_dir: Path):
    page_html = build_document(doc)
    title = f"{COMPANY} — {doc['title']}"
    page_html = set_doc_title(page_html, title)
    out_pdf = out_dir / f"{doc['id']}.pdf"

    font_config = FontConfiguration()
    HTML(string=page_html, base_url=str(out_dir)).write_pdf(
        str(out_pdf),
        stylesheets=[],
        font_config=font_config,
    )
    return out_pdf


def main():
    out_dir = DOCS / "pdf"
    out_dir.mkdir(exist_ok=True)
    print(f"Gerando PDFs em {out_dir}")
    for doc in DOCUMENTS:
        try:
            pdf = render(doc, out_dir)
            size = pdf.stat().st_size
            print(f"  OK {pdf.name} ({size/1024:.1f} KB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERRO {doc['id']}: {exc}")
    print("Concluído.")


if __name__ == "__main__":
    main()