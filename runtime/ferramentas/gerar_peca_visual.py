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

Storage: uma pasta por post em dados/pecas/, nomeada
`{post_id}-{slug-da-headline}/` — `post_id` primeiro garante unicidade e
ordenação cronológica no explorador de arquivos (tem a data embutida); o
slug (do título do slide 1 — a capa) é só pra achar visualmente. Dentro da
pasta, cada peça é `slide{ordem}.png` (ou `.mp4` pro reel, que só tem 1
peça mas ainda cai na subpasta do post). Ver `_pasta_post`/`_nome_peca`.
`post_id` vem do `execucao_id` da execução (planejador.py o injeta nos
argumentos). Numa regeneração parcial os `slides` não mudam (mesmo
roteiro aprovado), então a pasta calculada é sempre a mesma dentro da
execução — a peça reprovada é sobrescrita no lugar, nunca cria pasta nova.

Regeneração parcial (custo real observado): quando `pecas_urls_existentes` +
`indices_para_regenerar` vêm preenchidos (planejador.py monta isso a partir
de `autocritica_conteudo.indices_com_problema`), só as peças apontadas são
re-renderizadas — as outras são reaproveitadas como estão.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..adapters.fotos_estoque.base_adapter import Foto, FotoEstoqueAdapter
from ..adapters.fotos_estoque.unsplash_adapter import UnsplashAdapter
from ..geracao_visual.imagem.motor_template import motor_de
from ..geracao_visual.imagem.selecionar_template import LAYOUTS_COM_FOTO, montar_html
from ..geracao_visual.video.selecionar_video import selecionar_estrategia_video

DURACAO_ESTIMADA_REEL_SEGUNDOS = 8  # não é parâmetro real da API — só estimativa de custo

_ORIENTACAO_POR_LAYOUT = {"foto_split": "landscape", "capa": "portrait"}

_SLUG_MAX_LEN = 50


def _slugificar(texto: str) -> str:
    """minúsculo, sem acento (normaliza unicode), espaços/pontuação viram
    hífen, sem hífen duplicado nem nas pontas, truncado em ~50 chars
    cortando em hífen (não no meio de uma palavra)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    if len(slug) <= _SLUG_MAX_LEN:
        return slug
    cortado = slug[:_SLUG_MAX_LEN]
    return cortado.rsplit("-", 1)[0] if "-" in cortado else cortado


def _pasta_post(post_id: str | None, slides: list[dict[str, Any]]) -> str | None:
    """`{post_id}-{slug-da-headline}` — headline vem do título do slide 1
    (a capa; único slide em estatico/reel). Sem título (ou vazio), cai só
    no post_id sem sufixo. Sem post_id, None (ver _nome_peca)."""
    if not post_id:
        return None
    titulo = str((slides[0] if slides else {}).get("titulo") or "").strip()
    slug = _slugificar(titulo) if titulo else ""
    return f"{post_id}-{slug}" if slug else post_id


def _narracao(slides: list[dict[str, Any]]) -> str:
    blocos = []
    for s in slides:
        titulo = str(s.get("titulo") or "").strip()
        corpo = str(s.get("corpo") or "").strip()
        bloco = "\n".join(x for x in (titulo, corpo) if x)
        if bloco:
            blocos.append(bloco)
    return "\n\n".join(blocos)


def _nome_peca(pasta: str | None, slide: dict[str, Any], pos: int) -> str | None:
    """`{pasta}/slide{ordem}` — `pasta` vem de `_pasta_post` (uma por
    post). Sem pasta (ex: chamada direta em teste sem post_id), devolve
    None -> storage cai num hash."""
    if not pasta:
        return None
    ordem = slide.get("ordem") or (pos + 1)
    return f"{pasta}/slide{ordem}"


def _slide_pede_foto(slide: dict[str, Any]) -> bool:
    return (
        slide.get("tipo_layout") in LAYOUTS_COM_FOTO
        and bool(str(slide.get("consulta_foto") or "").strip())
    )


def _buscar_foto(
    slide: dict[str, Any], adapter: FotoEstoqueAdapter, *, ajustes: Any, pular: int, ids_evitar: set[str] | None = None,
) -> Foto:
    query = str(slide.get("consulta_foto") or "").strip()
    if ajustes:
        # regeneração: enviesa a busca pra vir uma foto diferente
        extra = " ".join(map(str, ajustes)) if isinstance(ajustes, (list, tuple)) else str(ajustes)
        query = f"{query} {extra}".strip()
    orientacao = _ORIENTACAO_POR_LAYOUT.get(slide.get("tipo_layout"), "portrait")
    return adapter.buscar_foto(query, orientacao=orientacao, pular=pular, ids_evitar=ids_evitar)


def _gerar_imagens(
    *,
    slides: list[dict[str, Any]],
    identidade_visual: dict[str, Any] | None,
    post_id: str | None,
    pecas_urls_existentes: list[str] | None,
    indices_para_regenerar: list[int] | None,
    ajustes: Any,
    foto_adapter: FotoEstoqueAdapter,
    ids_evitar_historico: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    total = len(slides)
    pasta = _pasta_post(post_id, slides)
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
    # `ids_usados` nasce pré-carregado com o histórico entre execuções
    # (memoria.fotos_usadas_recentes, via planejador.py) — o adapter evita
    # repetir tanto essas quanto as já usadas nos slides deste MESMO post.
    ids_usados: set[str] = set(ids_evitar_historico or [])
    fotos_novas: list[str] = []
    for pos in posicoes:
        slide = slides[pos]
        foto = _buscar_foto(slide, foto_adapter, ajustes=ajustes if regeneracao_parcial else None, pular=pular_foto, ids_evitar=ids_usados) \
            if _slide_pede_foto(slide) else None

        if foto and foto.foto_id:
            ids_usados.add(foto.foto_id)
            fotos_novas.append(foto.foto_id)

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
        nomes.append(_nome_peca(pasta, slide, pos))

    caminhos = motor_de(identidade_visual).renderizar_varios(htmls, nomes)
    for pos, caminho in zip(posicoes, caminhos):
        pecas_urls[pos] = caminho
    return [c for c in pecas_urls if c is not None], fotos_novas


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
    ids_evitar_historico: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """entrada: {slides, formato} (+ extensões internas) · saida: {pecas_urls: list, formato}"""
    if not slides:
        raise ValueError("gerar_peca_visual: `slides` vazio.")

    if formato == "reel":
        estrategia = selecionar_estrategia_video(carro_chefe=carro_chefe)
        nome_base = _nome_peca(_pasta_post(post_id, slides), slides[0], 0)
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

    pecas_urls, fotos_novas = _gerar_imagens(
        slides=slides,
        identidade_visual=identidade_visual,
        post_id=post_id,
        pecas_urls_existentes=pecas_urls_existentes,
        indices_para_regenerar=indices_para_regenerar,
        ajustes=ajustes,
        foto_adapter=foto_adapter or UnsplashAdapter(),
        ids_evitar_historico=ids_evitar_historico,
    )
    # motor de template + foto de estoque grátis => custo de imagem ~zero;
    # nada de `_custo` a reportar (decisoes-de-engenharia.md, seção 12).
    saida = {"pecas_urls": pecas_urls, "formato": formato}
    if fotos_novas:
        # chave interna consumida por executor.py — não faz parte do
        # contrato de saída de skills.md (mesmo padrão de `_custo`).
        saida["_fotos_usadas"] = fotos_novas
    return saida
