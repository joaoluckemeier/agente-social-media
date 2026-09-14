"""geracao_visual/imagem/selecionar_template.py — Strategy.

`tipo_layout` do slide -> arquivo de template + contexto preenchido (titulo,
corpo, design tokens, cabeçalho/rodapé fixo, contador de slide, foto em
data-URI quando o layout pede). Devolve a string HTML final pro
motor_template renderizar.

Os 7 tipos de layout são os de skills.md (nota ao final) / a seção
"Identidade Visual" de perfil-marca.md.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any

_DIR_TEMPLATES = Path(__file__).parent / "templates"

TIPOS_LAYOUT = (
    "capa",
    "texto_grande",
    "lista_numerada",
    "diagrama_processo",
    "comparacao",
    "foto_split",
    "cta",
)
_FALLBACK = "texto_grande"

# layouts que compõem com foto real (Unsplash) — os demais ignoram foto_bytes
LAYOUTS_COM_FOTO = ("foto_split", "capa")

_ESTILO_BASE = """\
<style>
  @import url('{{GOOGLE_FONTS_URL}}');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: {{LARGURA}}px; height: {{ALTURA}}px; }
  body {
    background: {{FUNDO}};
    color: {{TEXTO}};
    font-family: {{FAMILIA_CORPO}};
    font-weight: {{PESO_CORPO}};
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    position: relative;
    overflow: hidden;
  }
  .quadro { position: absolute; inset: 0; padding: 96px 90px; display: flex; flex-direction: column; }
  .cabecalho {
    display: flex; justify-content: space-between; align-items: center;
    font-family: {{FAMILIA_CORPO}}; font-weight: 700; font-size: 27px;
    letter-spacing: .01em;
  }
  .cabecalho .arraste { text-transform: uppercase; letter-spacing: .14em; font-size: 22px; opacity: .65; }
  .conteudo {
    flex: 1; min-height: 0; display: flex; flex-direction: column;
    justify-content: safe center; gap: 40px;
  }
  .titulo {
    font-family: {{FAMILIA_TITULO}}; font-weight: {{PESO_TITULO}};
    text-transform: uppercase; line-height: .95; font-size: 92px; letter-spacing: -.01em;
  }
  .corpo { font-size: 39px; line-height: 1.42; max-width: 94%; }
  .corpo p + p { margin-top: 24px; }
  .destaque { color: {{DESTAQUE}}; }
  .rodape { display: flex; align-items: center; justify-content: space-between; gap: 28px; }
  .rodape .linha { height: 3px; background: {{LINHA}}; flex: 1; opacity: .45; }
  .rodape .contador {
    font-family: {{FAMILIA_TITULO}}; font-weight: {{PESO_TITULO}};
    font-size: 30px; letter-spacing: .03em;
  }
</style>\
"""


def _fmt_inline(texto: str) -> str:
    """Escapa HTML e converte *ênfase* em cor de destaque."""
    esc = html.escape((texto or "").strip())
    return re.sub(r"\*([^*\n]+)\*", r'<span class="destaque">\1</span>', esc)


def _paragrafos(corpo: str) -> str:
    linhas = [l.strip() for l in (corpo or "").splitlines() if l.strip()]
    return "".join(f"<p>{_fmt_inline(l)}</p>" for l in linhas)


_PREFIXO_ITEM_RE = re.compile(r"^\s*(?:\d+\s*[\).\-–]?\s+|[-•–]\s+)")


def _itens(corpo: str) -> str:
    linhas = [l.strip() for l in (corpo or "").splitlines() if l.strip()]
    linhas = [_PREFIXO_ITEM_RE.sub("", l) for l in linhas]
    return "".join(f"<li>{_fmt_inline(l)}</li>" for l in linhas)


def _template_para(tipo_layout: str) -> str:
    tipo = tipo_layout if tipo_layout in TIPOS_LAYOUT else _FALLBACK
    arq = _DIR_TEMPLATES / f"{tipo}.html"
    if not arq.is_file():
        arq = _DIR_TEMPLATES / f"{_FALLBACK}.html"
    return arq.read_text(encoding="utf-8")


def montar_html(
    slide: dict[str, Any],
    *,
    identidade_visual: dict[str, Any],
    indice: int,
    total: int,
    foto_bytes: bytes | None = None,
    foto_mime: str = "image/jpeg",
) -> str:
    iv = identidade_visual or {}
    cores = iv.get("cores") or {}
    tipog = iv.get("tipografia") or {}
    dim = iv.get("dimensoes") or {}
    cab = iv.get("cabecalho") or {}
    rod = iv.get("rodape") or {}

    foto_uri = ""
    if foto_bytes:
        foto_uri = f"data:{foto_mime};base64,{base64.b64encode(foto_bytes).decode('ascii')}"
    altura_total = int(dim.get("altura", 1350))
    comprimento_corpo = len(str(slide.get("corpo", "") or ""))
    if comprimento_corpo > 220:
        altura_foto_split = int(altura_total * 0.32)
    elif comprimento_corpo > 120:
        altura_foto_split = int(altura_total * 0.40)
    else:
        altura_foto_split = int(altura_total * 0.47)
    
    mostrar_contador = bool(rod.get("mostrar_contador", True)) and total > 1
    contador = f"{indice}/{total}" if mostrar_contador else ""

    ctx: dict[str, str] = {
        "GOOGLE_FONTS_URL": str(tipog.get("google_fonts_url", "")),
        "LARGURA": str(dim.get("largura", 1080)),
        "ALTURA": str(dim.get("altura", 1350)),
        "FUNDO": str(cores.get("fundo", "#F1ECE4")),
        "TEXTO": str(cores.get("texto", "#1F1710")),
        "DESTAQUE": str(cores.get("destaque", "#C1622D")),
        "LINHA": str(cores.get("linha", cores.get("texto", "#1F1710"))),
        "FAMILIA_TITULO": str(tipog.get("familia_titulo", "sans-serif")),
        "FAMILIA_CORPO": str(tipog.get("familia_corpo", "sans-serif")),
        "PESO_TITULO": str(tipog.get("peso_titulo", 800)),
        "PESO_CORPO": str(tipog.get("peso_corpo", 400)),
        "ARROBA": html.escape(str(cab.get("arroba", ""))),
        "INDICADOR_ARRASTE": (
            html.escape(str(cab.get("indicador_arraste", ""))) if indice < total else ""
        ),
        "CONTADOR": html.escape(contador),
        "TITULO": _fmt_inline(slide.get("titulo", "")),
        "CORPO_HTML": _paragrafos(slide.get("corpo", "")),
        "ITENS_HTML": _itens(slide.get("corpo", "")),
        "FOTO_DATA_URI": foto_uri,
        "ALTURA_FOTO_SPLIT": str(altura_foto_split),
        "ESTILO_BASE": _ESTILO_BASE,
    }

    html_final = _template_para(slide.get("tipo_layout", ""))
    # 2 passadas: a 1ª inlina {{ESTILO_BASE}}, a 2ª resolve os {{TOKENS}}
    # que ele (e cada template) trazem dentro.
    for _ in range(2):
        for chave, valor in ctx.items():
            html_final = html_final.replace("{{" + chave + "}}", valor)
    return html_final
