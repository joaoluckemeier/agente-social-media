"""api/rotas/pecas.py — serve os PNGs gerados (dados/pecas/) por HTTP.

Existe só pra o front-end poder RENDERIZAR a peça em vez de mostrar o
caminho de disco da VPS (a lacuna documentada em
geracao_visual/base_estrategia.py). Nome de arquivo é a única entrada, e
vem de fora (o cliente HTTP repassa o que já viu num payload de
aprovações/posts) — 4 camadas de validação antes de tocar disco:

  1. regex fechado (aqui): só o formato exato que o agente gera;
  2. caminho resolvido continua dentro de dados/pecas/ (servico_agente.py);
  3. só .png é servido, nunca outra extensão (servico_agente.py);
  4. o nome precisa corresponder a uma peça REGISTRADA no banco — não só
     "existe um arquivo com esse nome na pasta" (servico_agente.py).

Mesma proteção das outras rotas: X-API-Key obrigatória, bind 127.0.0.1
(api/config.py) — nunca exposta direto, só o backend do front-end (já
autenticado, com tenant_scope) chama isto.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import exigir_api_key, identificar_chamador
from ..config import ConfigApi, carregar_config
from ..observabilidade import registrar_evento_api
from ..servico_agente import PecaInvalida, PecaNaoEncontrada, obter_peca_bytes

router = APIRouter(
    prefix="/pecas",
    tags=["pecas"],
    dependencies=[Depends(exigir_api_key)],
)

# convenção de agent.md: {post_id}_slide{ordem}.png, post_id = execucao_id
# (post_YYYY_MM_DD_<hex>) — fechado o suficiente pra nunca conter "/" nem
# "..", então já bloqueia path traversal por si só. A camada 2 (resolver +
# checar containment) em servico_agente.py é defesa em profundidade, não a
# única barreira.
_NOME_ARQUIVO_RE = re.compile(r"^post_[a-z0-9_]+_slide\d+\.png$")


@router.get("/{arquivo}")
async def get_peca(
    arquivo: str,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> Response:
    if not _NOME_ARQUIVO_RE.match(arquivo):
        registrar_evento_api(
            rota=f"/pecas/{arquivo}", metodo="GET", chamador=chamador,
            resultado="nome_invalido", nivel="alerta",
        )
        raise HTTPException(status_code=400, detail="nome de arquivo inválido")

    try:
        conteudo = obter_peca_bytes(config, arquivo)
    except PecaInvalida as exc:
        registrar_evento_api(
            rota=f"/pecas/{arquivo}", metodo="GET", chamador=chamador,
            resultado="invalida", nivel="alerta", detalhes={"motivo": str(exc)},
        )
        raise HTTPException(status_code=400, detail="nome de arquivo inválido") from exc
    except PecaNaoEncontrada as exc:
        registrar_evento_api(
            rota=f"/pecas/{arquivo}", metodo="GET", chamador=chamador,
            resultado="nao_encontrada", nivel="alerta",
        )
        raise HTTPException(status_code=404, detail="peça não encontrada") from exc

    registrar_evento_api(rota=f"/pecas/{arquivo}", metodo="GET", chamador=chamador, resultado="ok")
    return Response(
        content=conteudo,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
