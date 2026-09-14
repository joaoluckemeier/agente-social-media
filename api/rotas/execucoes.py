"""api/rotas/execucoes.py — disparar / acompanhar execuções (Etapa 2 e 3).

POST /execucoes              — dispara um `rodar` em background. Antes:
                                - trava de execução concorrente (409);
                                - rate limit local por hora/dia (429) — 2ª camada.
GET  /execucoes/aguardando   — execuções paradas em PERGUNTAR_USUARIO, esperando
                                o operador corrigir a causa (Etapa 3).
GET  /execucoes/{id}         — estado da execução.
GET  /execucoes/{id}/trace   — trace bruto e completo (Etapa 3). O filtro por
                                papel (operador vê tudo; cliente vê resumo
                                amigável, sem custo/modelo/erro cru) é feito
                                no backend do front-end, não aqui.
POST /execucoes/{id}/descartar — libera a trava de uma execução suspensa ou
                                aguardando intervenção (Etapa 3). 404 se não
                                existe, 409 se está 'rodando' ou já descartada
                                — nunca 200 sem ter descartado de verdade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import exigir_api_key, identificar_chamador
from ..config import ConfigApi, carregar_config
from ..esquemas import AguardandoOut, DisparoIn, ExecucaoOut
from ..guardas import ExecucaoEmAndamento, RateLimitLocalAtingido
from ..observabilidade import registrar_evento_api
from ..servico_agente import (
    ExecucaoNaoDescartavel,
    ExecucaoNaoEncontrada,
    descartar_execucao,
    disparar_execucao,
    estado_execucao,
    listar_execucoes_aguardando,
    obter_trace,
)

router = APIRouter(
    prefix="/execucoes",
    tags=["execucoes"],
    dependencies=[Depends(exigir_api_key)],
)


@router.post("", response_model=ExecucaoOut, status_code=202)
async def post_execucao(
    corpo: DisparoIn,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> ExecucaoOut:
    try:
        r = disparar_execucao(
            config, entrada=corpo.entrada, formato=corpo.formato, chamador=chamador
        )
    except ExecucaoEmAndamento as exc:
        registrar_evento_api(
            rota="/execucoes", metodo="POST", chamador=chamador, resultado="conflito",
            nivel="alerta", execucao_id=exc.execucao_id,
            detalhes={"estado": exc.estado},
        )
        raise HTTPException(
            status_code=409,
            detail={"erro": "execucao_em_andamento", "execucao_id": exc.execucao_id,
                    "estado": exc.estado},
        ) from exc
    except RateLimitLocalAtingido as exc:
        registrar_evento_api(
            rota="/execucoes", metodo="POST", chamador=chamador, resultado="rate_limit",
            nivel="alerta", detalhes={"janela": exc.janela, "limite": exc.limite},
        )
        raise HTTPException(
            status_code=429,
            detail={"erro": "rate_limit", "janela": exc.janela, "limite": exc.limite},
        ) from exc

    registrar_evento_api(
        rota="/execucoes", metodo="POST", chamador=chamador, resultado="disparada",
        execucao_id=r["execucao_id"], detalhes={"formato": corpo.formato},
    )
    return ExecucaoOut(execucao_id=r["execucao_id"], estado=r["estado"], formato=corpo.formato,
                       entrada=corpo.entrada)


@router.get("/aguardando", response_model=AguardandoOut)
async def get_aguardando(
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> AguardandoOut:
    execucoes = listar_execucoes_aguardando(config)
    registrar_evento_api(
        rota="/execucoes/aguardando", metodo="GET", chamador=chamador, resultado="ok",
        detalhes={"quantidade": len(execucoes)},
    )
    return AguardandoOut(execucoes=[ExecucaoOut(**e) for e in execucoes])


@router.get("/{execucao_id}", response_model=ExecucaoOut)
async def get_execucao(
    execucao_id: str,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> ExecucaoOut:
    est = estado_execucao(config, execucao_id)
    if est is None:
        raise HTTPException(status_code=404, detail="execução não encontrada")
    return ExecucaoOut(**est)


@router.get("/{execucao_id}/trace")
async def get_trace(
    execucao_id: str,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> dict:
    """Trace bruto e completo (hooks.md) da execução — sem filtro de papel:
    quem decide o que cada papel vê é o backend do front-end, não o agente
    (o agente não sabe o que é 'operador'/'cliente'). `404` se não é a
    execução mais recente (dados/trace.json guarda só uma por vez)."""
    bruto = obter_trace(config, execucao_id)
    if bruto is None:
        raise HTTPException(
            status_code=404,
            detail="trace não disponível pra esta execução (só a mais recente é mantida)",
        )
    registrar_evento_api(
        rota=f"/execucoes/{execucao_id}/trace", metodo="GET", chamador=chamador,
        resultado="ok", execucao_id=execucao_id,
    )
    return bruto


@router.post("/{execucao_id}/descartar", response_model=ExecucaoOut)
async def post_descartar(
    execucao_id: str,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> ExecucaoOut:
    try:
        est = descartar_execucao(config, execucao_id, chamador=chamador)
    except ExecucaoNaoEncontrada as exc:
        registrar_evento_api(
            rota=f"/execucoes/{execucao_id}/descartar", metodo="POST", chamador=chamador,
            resultado="nao_encontrada", nivel="alerta", execucao_id=execucao_id,
        )
        raise HTTPException(status_code=404, detail="execução não encontrada") from exc
    except ExecucaoNaoDescartavel as exc:
        registrar_evento_api(
            rota=f"/execucoes/{execucao_id}/descartar", metodo="POST", chamador=chamador,
            resultado="conflito", nivel="alerta", execucao_id=execucao_id,
            detalhes={"motivo": str(exc)},
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    registrar_evento_api(
        rota=f"/execucoes/{execucao_id}/descartar", metodo="POST", chamador=chamador,
        resultado="descartada", nivel="alerta", execucao_id=execucao_id,
    )
    return ExecucaoOut(**est)
