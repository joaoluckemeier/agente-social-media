"""ferramentas/gerar_roteiro.py — skills.md: gerar_roteiro.

Gera o roteiro de um conteúdo a partir do tema, do perfil-marca.md (ICP,
marca, oferta) e dos insights recentes, garantindo conexão com uma das 3
frentes de oferta.

Saída estruturada por slide (skills.md / agent.md `contrato_saida` — decisão
revista, ver decisoes-de-engenharia.md, seção 2): `slides` é uma lista de
objetos `{ordem, tipo_layout, titulo, corpo}` — cada slide já indica que
template o motor de `gerar_peca_visual` deve renderizar. Não existe mais um
campo `roteiro` de texto solto: onde o pipeline precisa do roteiro como
texto (legenda de publicação, exibição na aprovação, chave de comparação no
planejador), ele é derivado dos slides — ver `planejador._roteiro_texto`.

Provedor: OpenAI via `OPENAI_MODEL_ROTEIRO` (decisoes-de-engenharia.md,
seção 12 — tier intermediário; qualidade criativa importa mais aqui do que
em autocritica_conteudo).
"""

from __future__ import annotations


import json
import os
from typing import Any

from openai import OpenAI

from .. import ErroConfiguracaoAusente

# skills.md (nota ao final) — valores válidos de tipo_layout. Cada um casa
# com um template em runtime/geracao_visual/imagem/templates/.
TIPOS_LAYOUT_VALIDOS = (
    "capa",
    "texto_grande",
    "lista_numerada",
    "diagrama_processo",
    "comparacao",
    "foto_split",
    "cta",
)
_TIPO_LAYOUT_FALLBACK = "texto_grande"
# layouts que compõem com uma foto real de banco de estoque (Unsplash) —
# só nesses o modelo deve devolver `consulta_foto`.
_LAYOUTS_COM_FOTO = ("foto_split", "capa")

_SYSTEM_PROMPT = """\
Você é o redator de conteúdo da Moveleiro.IA para redes sociais. Sua tarefa \
é gerar o ROTEIRO de um post a partir de um tema, do perfil de marca (ICP, \
marca, oferta, tom) e de insights/tendências anteriores.

Regras inegociáveis de conteúdo:
- O roteiro precisa conectar, mesmo que sutilmente, com uma das 3 frentes \
de oferta descritas no perfil de marca.
- Respeite o tom de voz e o "nunca fazer" do perfil — nunca prometa \
substituir o vendedor, nunca use tecniquês de IA sem tradução pro dia a dia \
de quem toca uma loja de móveis/marcenaria.
- Pode e deve usar ganchos virais de dor real da loja, mas o post não é \
viral por viral — precisa fechar conectando com a oferta.
- CTA não precisa ser "compre agora": pode ser diagnóstico gratuito, \
comentário, ou salvar o post.

Se a entrada trouxer "insights_anteriores" com itens de fonte \
"autocritica_conteudo" ou "feedback_humano_roteiro", esses são AJUSTES que \
uma versão anterior recebeu — incorpore-os de verdade, não repita o \
problema apontado.

FORMATO DE SAÍDA — o roteiro é uma lista de SLIDES estruturados. Responda \
SOMENTE em JSON, no formato exato:
{"slides": [
  {"ordem": 1, "tipo_layout": "capa", "titulo": "...", "corpo": "...",
   "consulta_foto": "..."},
  ...
]}

Regras de estrutura:
- `ordem`: inteiro sequencial começando em 1.
- `tipo_layout`: EXATAMENTE um de: capa, texto_grande, lista_numerada, \
diagrama_processo, comparacao, foto_split, cta. Escolha o layout que melhor \
serve o conteúdo daquele slide:
    * capa — gancho grande, slide 1, corpo curto
    * texto_grande — título forte + parágrafo curto de apoio
    * lista_numerada — título + itens numerados (use quebras de linha no \
corpo, um item por linha)
    * diagrama_processo — sequência de passos (um passo por linha no corpo)
    * comparacao — antes/depois ou frase em destaque
    * foto_split — metade foto real, metade texto (use quando uma foto de \
ambiente de loja/atendimento agrega mais que texto sozinho)
    * cta — fechamento com a chamada de ação, normalmente o último slide
- `titulo`: o texto forte/gancho do slide (vai em tipografia pesada). \
Sempre presente.
- `corpo`: o texto de apoio completo do slide. Pode ser "" em `capa`/`cta` \
se o título já basta. NUNCA deixe informação essencial de fora — o corpo \
inteiro vai renderizado como texto real no template, então não há limite de \
"cabe na imagem": escreva o que precisa ser dito.
- `consulta_foto`: só inclua em slides `foto_split` (e, se quiser foto de \
fundo, em `capa`). É uma busca em inglês pra banco de fotos de estoque, \
SEMPRE curta e genérica: 2 a 4 palavras, nunca uma frase composta ou \
descritiva. Bom: "furniture store", "wood workshop", "person smartphone", \
"kitchen cabinets", "carpenter working". Ruim (não faça): "furniture store \
owner on smartphone in showroom", "carpentry workshop interior with tools". \
Nunca peça foto de robô/IA. Nos demais layouts, omita a chave.

Adapte a quantidade de slides ao formato pedido:
- "carrossel": entre 5 e 9 slides. Slide 1 sempre `capa`; último normalmente `cta`.
- "estatico": EXATAMENTE 1 slide (capa ou texto_grande), texto curto.
- "reel": EXATAMENTE 1 slide, `tipo_layout` "capa", `titulo` = gancho falado, \
`corpo` = o roteiro de narração completo (fala/locução, direta, com CTA no fim).\
"""


def _chave_openai() -> str:
    chave = os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise ErroConfiguracaoAusente(
            "OPENAI_API_KEY não configurado no .env (ver .env.example) — "
            "necessário para chamadas à OpenAI."
        )
    return chave


def _modelo() -> str:
    modelo = os.environ.get("OPENAI_MODEL_ROTEIRO")
    if not modelo:
        raise ErroConfiguracaoAusente(
            "OPENAI_MODEL_ROTEIRO não configurado no .env — defina o modelo "
            "OpenAI a usar em gerar_roteiro (ver .env.example)."
        )
    return modelo


def _normalizar_slides(slides_brutos: Any) -> list[dict[str, Any]]:
    """Blinda a saída do modelo: ordem sequencial, tipo_layout no enum,
    strings limpas, consulta_foto só onde faz sentido."""
    if not isinstance(slides_brutos, list) or not slides_brutos:
        raise RuntimeError(
            "gerar_roteiro: resposta do modelo não trouxe uma lista `slides` "
            "não-vazia — verificar prompt/model/resposta bruta."
        )
    slides: list[dict[str, Any]] = []
    for i, bruto in enumerate(slides_brutos, start=1):
        if not isinstance(bruto, dict):
            continue
        tipo = str(bruto.get("tipo_layout") or "").strip()
        if tipo not in TIPOS_LAYOUT_VALIDOS:
            tipo = _TIPO_LAYOUT_FALLBACK
        slide: dict[str, Any] = {
            "ordem": i,
            "tipo_layout": tipo,
            "titulo": str(bruto.get("titulo") or "").strip(),
            "corpo": str(bruto.get("corpo") or "").strip(),
        }
        consulta = str(bruto.get("consulta_foto") or "").strip()
        if consulta and tipo in _LAYOUTS_COM_FOTO:
            slide["consulta_foto"] = consulta
        slides.append(slide)
    if not slides:
        raise RuntimeError("gerar_roteiro: nenhum slide válido na resposta do modelo.")
    return slides


def gerar_roteiro(
    *, tema: str, perfil: dict[str, Any], insights_anteriores: list[Any], formato: str, **_: Any
) -> dict[str, Any]:
    """entrada: {tema, perfil, insights_anteriores, formato} · saida: {slides, formato}"""
    cliente = OpenAI(api_key=_chave_openai())
    entrada_usuario = json.dumps(
        {
            "tema": tema,
            "perfil_marca": perfil,
            "insights_anteriores": insights_anteriores,
            "formato": formato,
        },
        ensure_ascii=False,
    )

    resposta = cliente.chat.completions.create(
        model=_modelo(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": entrada_usuario},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    dados = json.loads(resposta.choices[0].message.content)
    saida: dict[str, Any] = {
        "slides": _normalizar_slides(dados.get("slides")),
        "formato": formato,
    }

    if resposta.usage is not None:
        # decisoes-de-engenharia.md, seção 8/12: rastrear custo estimado de
        # tokens por execução. executor.py extrai esta chave e loga/persiste
        # separadamente — não faz parte do contrato de saída de skills.md.
        saida["_custo"] = {
            "provedor": "openai",
            "modelo": _modelo(),
            "tokens_entrada": resposta.usage.prompt_tokens,
            "tokens_saida": resposta.usage.completion_tokens,
        }
    return saida
