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
Você é um copywriter sênior especializado em conteúdo B2B para redes \
sociais, com domínio de storytelling, estrutura persuasiva e ritmo de \
leitura — cada frase existe pra puxar a atenção pra próxima. Você escreve \
pra Moveleiro.IA. Sua tarefa é gerar o ROTEIRO de um post a partir de um \
tema, do perfil de marca (ICP, marca, oferta, tom) e de insights/tendências \
anteriores.

Regras inegociáveis de conteúdo:
- O roteiro precisa conectar, mesmo que sutilmente, com uma das 3 frentes \
de oferta descritas no perfil de marca.
- Respeite o tom de voz e o "nunca fazer" do perfil — nunca prometa \
substituir o vendedor, nunca use tecniquês de IA sem tradução pro dia a dia \
de quem toca uma loja de móveis/marcenaria.
- Pode e deve usar ganchos virais de dor real da loja, mas o post não é \
viral por viral — precisa fechar conectando com a oferta.
- CTA nunca é "compre agora" — pode ser diagnóstico gratuito ou
  comentário, por exemplo. Mas cada post tem UMA ÚNICA CTA, nunca
  mais de uma opção competindo entre si (ex: "diagnóstico no link
  da bio" OU "comente DIAGNÓSTICO" — nunca as duas juntas no mesmo post).
- NUNCA inclua número de R$ de faturamento/receita prometido, nem \
estimativa numérica de resultado financeiro — mesmo que pareça realista, \
isso vira propaganda enganosa. Ganho pode ser descrito qualitativamente \
(mais visita agendada, lead que não esfria), nunca em R$.

Mecanismo e CTA:
- No fechamento/CTA do post, sempre que fizer sentido, nomeie o "Sistema \
Comercial Moveleiro" como a solução única — nunca como "IA" genérica, e \
nunca mencionando nome de agente/ferramenta interna (é implementação, não \
é o que aparece pro cliente final).
- "Vazamento Silencioso de Vendas", "Janela de Ouro" e "Presença Digital \
Fraca" são vocabulário fixo da marca — reutilize-os ao longo de vários \
posts, não é preciso inventar nome novo de problema a cada post.
- As "Provas de sustentação" e "Objeções a quebrar" do perfil de marca são \
material de apoio: use com moderação (não cite estatística em todo post), \
e nunca cite HubSpot como fonte.

Variedade entre posts:
- Se a entrada trouxer "temas_recentes" (temas de posts anteriores), não \
repita a mesma estrutura de gancho nem a mesma frente/mecanismo nomeado \
desses temas — varie o TIPO de gancho e a FRENTE do problema, não só a \
palavra.
- Frente do problema (alterne entre elas): Frente 1 (geração de demanda) \
— anúncio que não converte, tráfego caro que esfria, ou "Presença Digital \
Fraca"; Frente 2 (atendimento/fechamento) — "Vazamento Silencioso de \
Vendas", "Janela de Ouro" (o período curto pra responder antes de perder \
a atenção pro concorrente).
- Tipo de gancho (alterne entre eles): pergunta direta, confissão de erro \
comum ("a maioria das lojas comete esse erro..."), estatística/número \
(usando as "Provas de sustentação", nunca citando HubSpot), contraste \
antes-depois, ou abrir citando um dos nomes do mecanismo ("vazamento \
silencioso", "janela de ouro", "presença digital fraca") direto no gancho.
- Nunca repita a mesma combinação de frente + tipo de gancho dos temas \
recentes duas vezes seguidas.

Se a entrada trouxer "insights_anteriores" com itens de fonte \
"autocritica_conteudo" ou "feedback_humano_roteiro", esses são AJUSTES que \
uma versão anterior recebeu — incorpore-os de verdade, não repita o \
problema apontado.

Auto-checagem de coerência (antes de responder): releia o conjunto de \
slides como se fosse o leitor passando o dedo no carrossel, um slide de \
cada vez. Pra cada slide, o título precisa conectar de verdade com o corpo \
dele — nunca um título que promete uma coisa e o corpo entrega outra. E a \
sequência entre slides precisa ter progressão lógica: não é uma lista de \
afirmações soltas sobre o mesmo tema, é uma linha de raciocínio que avança \
— cada slide parte de onde o anterior parou, constrói em cima dele, até \
chegar no CTA. Se notar título e corpo desconectados, ou um salto sem \
lógica entre dois slides, corrija antes de responder — não é aceitável \
entregar assim e deixar pra autocrítica pegar depois.

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
SE HOUVER MAIS DE UM slide com `consulta_foto` no mesmo post, cada busca \
precisa ser DIFERENTE e específica pro conteúdo daquele slide — nunca \
repita o mesmo termo genérico do nicho em dois slides (ex: não use \
"furniture store" duas vezes no mesmo post; varie entre termos como \
"furniture store", "carpenter working", "person smartphone" conforme o que \
cada slide especificamente mostra). \
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
    *,
    tema: str,
    perfil: dict[str, Any],
    insights_anteriores: list[Any],
    formato: str,
    temas_recentes: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """entrada: {tema, perfil, insights_anteriores, formato} · saida: {slides, formato}"""
    cliente = OpenAI(api_key=_chave_openai())
    entrada_usuario = json.dumps(
        {
            "tema": tema,
            "perfil_marca": perfil,
            "insights_anteriores": insights_anteriores,
            "formato": formato,
            "temas_recentes": temas_recentes or [],
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
