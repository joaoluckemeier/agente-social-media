"""api/rotas/perfil.py — ler e atualizar o perfil-marca.md real.

O front-end mostra um formulário estruturado (nunca YAML cru). Ao salvar,
chama `PUT /perfil` aqui — e é ESTA casca que reescreve o
`perfil-marca.md` que o runtime consome via `--perfil`. O front-end nunca
escreve nesse arquivo por fora (arquitetura.md).

A escrita passa pela mesma validação de "perfil completo" que o
`planejador.py` e o comando `validar` aplicam (ver servico_agente.py) —
seções obrigatórias ausentes => 422, arquivo real intacto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import exigir_api_key, identificar_chamador
from ..config import ConfigApi, carregar_config
from ..esquemas import PerfilIn, PerfilOut
from ..observabilidade import registrar_evento_api
from ..servico_agente import PerfilInvalido, escrever_perfil, ler_perfil

router = APIRouter(
    prefix="/perfil",
    tags=["perfil"],
    dependencies=[Depends(exigir_api_key)],
)


@router.get("", response_model=PerfilOut)
async def get_perfil(
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> PerfilOut:
    estrutura = ler_perfil(config)
    registrar_evento_api(
        rota="/perfil",
        metodo="GET",
        chamador=chamador,
        resultado="ok",
        detalhes={"existe": estrutura["existe"], "faltando": estrutura["secoes_faltando"]},
    )
    return PerfilOut(**estrutura)


@router.put("", response_model=PerfilOut)
async def put_perfil(
    corpo: PerfilIn,
    config: ConfigApi = Depends(carregar_config),
    chamador: str = Depends(identificar_chamador),
) -> PerfilOut:
    dados = corpo.model_dump(exclude={"nome_marca"})
    try:
        estrutura = escrever_perfil(config, dados, nome_marca=corpo.nome_marca)
    except PerfilInvalido as exc:
        registrar_evento_api(
            rota="/perfil",
            metodo="PUT",
            chamador=chamador,
            resultado="recusado_perfil_invalido",
            nivel="alerta",
            detalhes={"secoes_faltando": exc.secoes_faltando},
        )
        raise HTTPException(
            status_code=422,
            detail={
                "erro": "perfil_incompleto",
                "secoes_faltando": exc.secoes_faltando,
            },
        ) from exc

    registrar_evento_api(
        rota="/perfil",
        metodo="PUT",
        chamador=chamador,
        resultado="ok",
        nivel="alerta",  # edição de perfil é ação de mudança — registra como alerta
        detalhes={"caminho": str(config.perfil_path)},
    )
    return PerfilOut(**estrutura)
