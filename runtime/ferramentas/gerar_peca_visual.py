"""ferramentas/gerar_peca_visual.py — skills.md: gerar_peca_visual.

Gera a peça visual final a partir dos `slides` do roteiro aprovado.

- `estatico` / `carrossel` -> **motor de template** (código, não IA
  generativa): para cada slide, `selecionar_template` escolhe o template
  pelo `tipo_layout` e `motor_template` renderiza HTML/CSS -> PNG com os
  design tokens de `perfil-marca.md` (`identidade_visual`). Quando o layout
  pede foto (`foto_split`, `capa` com `consulta_foto`), a imagem vem do
  `FotoEstoqueAdapter` (Unsplash) — nunca de IA. Custo ~zero.
- `reel` -> vídeo via Veo (Gemini), tier padrão por default
  (`geracao_visual/video/selecionar_video.py`).

decisoes-de-engenharia.md, seção 2. O contrato de skills.md declara
`saida: {peca_url}`; como um carrossel tem várias peças (1 por slide), a
saída real é `pecas_urls: list[str]` — extensão documentada, consumida do
mesmo jeito por aprovação/publicação.

Nome de arquivo de cada peça: `{post_id}_slide{ordem}.png` (convenção de
agent.md). `post_id` vem do `execucao_id` da execução (planejador.py o
injeta nos argumentos); `ordem` é o campo do slide. Numa regeneração
parcial o nome é o mesmo, então a peça reprovada é sobrescrita no lugar.

Regeneração parcial (custo real observado): quando `pecas_urls_existentes` +
`indices_para_regenerar` vêm preenchidos (planejador.py monta isso a partir
de `autocritica_conteudo.indices_com_problema`), só as peças apontadas são
re-renderizadas — as outras são reaproveitadas como estão.
"""

from __future__ import annotations

from typing import Any

from ..adapters.fotos_estoque.base_adapter import Foto, FotoEstoqueAdapter
from ..adapters.fotos_estoque.unsplash_adapter import UnsplashAdapter
from ..geracao_visual.imagem.motor_template import motor_de
from ..geracao_visual.imagem.selecionar_template import LAYOUTS_COM_FOTO, montar_html
from ..geracao_visual.video.selecionar_video import selecionar_estrategia_video

DURACAO_ESTIMADA_REEL_SEGUNDOS = 8  # não é parâmetro real da API — só estimativa de custo

_ORIENTACAO_POR_LAYOUT = {"foto_split": "landscape", "capa": "portrait"}


def _narracao(slides: list[dict[str, Any]]) -> str:
    blocos = []
    for s in slides:
        titulo = str(s.get("titulo") or "").strip()
        corpo = str(s.get("corpo") or "").strip()
        bloco = "\n".join(x for x in (titulo, corpo) if x)
        if bloco:
            blocos.append(bloco)
    return "\n\n".join(blocos)


def _nome_peca(post_id: str | None, slide: dict[str, Any], pos: int) -> str | None:
    """agent.md: `{post_id}_slide{ordem}`. Sem post_id (ex: chamada direta
    em teste), devolve None -> storage cai num hash."""
    if not post_id:
        return None
    ordem = slide.get("ordem") or (pos + 1)
    return f"{post_id}_slide{ordem}"


def _slide_pede_foto(slide: dict[str, Any]) -> bool:
    return (
        slide.get("tipo_layout") in LAYOUTS_COM_FOTO
        and bool(str(slide.get("consulta_foto") or "").strip())
    )


def _buscar_foto(
    slide: dict[str, Any], adapter: FotoEstoqueAdapter, *, ajustes: Any, pular: int
) -> Foto:
    query = str(slide.get("consulta_foto") or "").strip()
    if ajustes:
        # regeneração: enviesa a busca pra vir uma foto diferente
        extra = " ".join(map(str, ajustes)) if isinstance(ajustes, (list, tuple)) else str(ajustes)
        query = f"{query} {extra}".strip()
    orientacao = _ORIENTACAO_POR_LAYOUT.get(slide.get("tipo_layout"), "portrait")
    return adapter.buscar_foto(query, orientacao=orientacao, pular=pular)


def _gerar_imagens(
    *,
    slides: list[dict[str, Any]],
    identidade_visual: dict[str, Any] | None,
    post_id: str | None,
    pecas_urls_existentes: list[str] | None,
    indices_para_regenerar: list[int] | None,
    ajustes: Any,
    foto_adapter: FotoEstoqueAdapter,
) -> list[str]:
    total = len(slides)
    regeneracao_parcial = bool(
        pecas_urls_existentes
        and indices_para_regenerar
        and len(pecas_urls_existentes) == total
    )

    if regeneracao_parcial:
        pecas_urls: list[str | None] = list(pecas_urls_existentes)  # type: ignore[arg-type]
        posicoes = [i - 1 for i in indices_para_regenerar if 1 <= i <= total]  # 1-based
        pular_foto = 1  # pega o 2º resultado da Unsplash, não o mesmo de antes
    else:
        pecas_urls = [None] * total
        posicoes = list(range(total))
        pular_foto = 0

    htmls: list[str] = []
    nomes: list[str | None] = []
    for pos in posicoes:
        slide = slides[pos]
        foto = _buscar_foto(slide, foto_adapter, ajustes=ajustes if regeneracao_parcial else None, pular=pular_foto) \
            if _slide_pede_foto(slide) else None
        htmls.append(
            montar_html(
                slide,
                identidade_visual=identidade_visual or {},
                indice=pos + 1,
                total=total,
                foto_bytes=foto.dados if foto else None,
                foto_mime=foto.mime if foto else "image/jpeg",
            )
        )
        nomes.append(_nome_peca(post_id, slide, pos))

    caminhos = motor_de(identidade_visual).renderizar_varios(htmls, nomes)
    for pos, caminho in zip(posicoes, caminhos):
        pecas_urls[pos] = caminho
    return [c for c in pecas_urls if c is not None]


def gerar_peca_visual(
    *,
    slides: list[dict[str, Any]],
    formato: str,
    identidade_visual: dict[str, Any] | None = None,
    post_id: str | None = None,
    carro_chefe: bool = False,
    pecas_urls_existentes: list[str] | None = None,
    indices_para_regenerar: list[int] | None = None,
    ajustes: Any = None,
    foto_adapter: FotoEstoqueAdapter | None = None,
    **_: Any,
) -> dict[str, Any]:
    """entrada: {slides, formato} (+ extensões internas) · saida: {pecas_urls: list, formato}"""
    if not slides:
        raise ValueError("gerar_peca_visual: `slides` vazio.")

    if formato == "reel":
        estrategia = selecionar_estrategia_video(carro_chefe=carro_chefe)
        nome_base = _nome_peca(post_id, slides[0], 0)
        saida_peca = estrategia.gerar(roteiro=_narracao(slides), formato=formato, nome_base=nome_base)
        usd = DURACAO_ESTIMADA_REEL_SEGUNDOS * estrategia.custo_usd_por_segundo
        return {
            "pecas_urls": [saida_peca["peca_url"]],
            "formato": formato,
            "_custo": {"provedor": "gemini", "modelo": "veo", "usd_estimado": round(usd, 4)},
        }

    if formato not in ("estatico", "carrossel"):
        raise ValueError(
            f"gerar_peca_visual: formato desconhecido {formato!r} "
            f"(esperado: reel | carrossel | estatico)"
        )

    pecas_urls = _gerar_imagens(
        slides=slides,
        identidade_visual=identidade_visual,
        post_id=post_id,
        pecas_urls_existentes=pecas_urls_existentes,
        indices_para_regenerar=indices_para_regenerar,
        ajustes=ajustes,
        foto_adapter=foto_adapter or UnsplashAdapter(),
    )
    # motor de template + foto de estoque grátis => custo de imagem ~zero;
    # nada de `_custo` a reportar (decisoes-de-engenharia.md, seção 12).
    return {"pecas_urls": pecas_urls, "formato": formato}
