"""api/rotas/posts.py — histórico de posts (leitura).

Expõe a tabela `posts` do agent DB (decisoes-de-engenharia.md, seção 3) —
a mesma que `upsert_post` preenche ao fim de um ciclo publicado. Só
leitura: a casca HTTP nunca edita `posts` por fora do runtime.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import exigir_api_key, identificar_chamador
from ..config import ConfigApi, carregar_config
from ..esquemas import HistoricoOut, PostOut
from ..observabilidade import registrar_evento_api
from ..servico_agente import buscar_post, listar_posts

router = APIRouter(
    prefix="/posts",
    tags=["posts"],
    dependencies=[Depends(exigir_api_key)],
)


@router.get("", response_model=HistoricoOut)
async def get_historico(
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> HistoricoOut:
    posts = listar_posts(config, limite=limite, offset=offset)
    registrar_evento_api(
        rota="/posts",
        metodo="GET",
        chamador=chamador,
        resultado="ok",
        detalhes={"retornados": len(posts), "limite": limite, "offset": offset},
    )
    return HistoricoOut(
        posts=[PostOut(**p) for p in posts], limite=limite, offset=offset
    )


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> PostOut:
    post = buscar_post(config, post_id)
    if post is None:
        registrar_evento_api(
            rota=f"/posts/{post_id}",
            metodo="GET",
            chamador=chamador,
            resultado="nao_encontrado",
            nivel="alerta",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="post não encontrado"
        )
    registrar_evento_api(
        rota=f"/posts/{post_id}", metodo="GET", chamador=chamador, resultado="ok"
    )
    return PostOut(**post)
