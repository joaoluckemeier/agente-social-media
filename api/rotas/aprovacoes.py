"""api/rotas/aprovacoes.py — fila de aprovação (Etapa 2).

GET  /aprovacoes/pendentes        — roteiro/visual/publicação aguardando decisão
POST /aprovacoes/{id}/decidir     — grava a decisão e retoma o ciclo

A decisão em si não é validada aqui: é gravada e consumida pelo loop do
próprio agente ao ser retomado (mesmas regras de rules.md/planner.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import exigir_api_key, identificar_chamador
from ..config import ConfigApi, carregar_config
from ..esquemas import (
    AprovacaoPendenteOut,
    DecisaoIn,
    DecisaoOut,
    PendentesOut,
)
from ..observabilidade import registrar_evento_api
from ..servico_agente import (
    AprovacaoNaoPendente,
    decidir_aprovacao,
    listar_aprovacoes_pendentes,
)

router = APIRouter(
    prefix="/aprovacoes",
    tags=["aprovacoes"],
    dependencies=[Depends(exigir_api_key)],
)


@router.get("/pendentes", response_model=PendentesOut)
async def get_pendentes(
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> PendentesOut:
    pendentes = listar_aprovacoes_pendentes(config)
    registrar_evento_api(
        rota="/aprovacoes/pendentes", metodo="GET", chamador=chamador,
        resultado="ok", detalhes={"quantidade": len(pendentes)},
    )
    return PendentesOut(
        pendentes=[
            AprovacaoPendenteOut(
                id=p["id"], execucao_id=p["execucao_id"], etapa=p["etapa"],
                peca=p["peca"], criado_em=p["criado_em"],
            )
            for p in pendentes
        ]
    )


@router.post("/{aprovacao_id}/decidir", response_model=DecisaoOut)
async def post_decidir(
    aprovacao_id: str,
    corpo: DecisaoIn,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> DecisaoOut:
    try:
        r = decidir_aprovacao(
            config, aprovacao_id,
            aprovado=corpo.aprovado, feedback=corpo.feedback, chamador=chamador,
        )
    except AprovacaoNaoPendente as exc:
        registrar_evento_api(
            rota=f"/aprovacoes/{aprovacao_id}/decidir", metodo="POST", chamador=chamador,
            resultado="conflito", nivel="alerta", detalhes={"motivo": str(exc)},
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    ap = r["aprovacao"]
    registrar_evento_api(
        rota=f"/aprovacoes/{aprovacao_id}/decidir", metodo="POST", chamador=chamador,
        resultado=f"{'aprovado' if corpo.aprovado else 'reprovado'}:{ap['etapa']}",
        nivel="alerta", execucao_id=ap["execucao_id"],
    )
    return DecisaoOut(
        aprovacao_id=ap["id"], etapa=ap["etapa"], aprovado=bool(ap["aprovado"]),
        execucao_retomada=r["execucao_retomada"],
    )
