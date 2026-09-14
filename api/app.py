"""api/app.py — aplicação FastAPI da casca HTTP do agente-social-media.

Subir (a partir de ~/agents/agente-social-media/, com o venv do agente):

    uvicorn api.app:app --host 127.0.0.1 --port 8790
    # ou, respeitando AGENTE_API_HOST/PORT do .env:
    python -m api.app

NUNCA suba com --host 0.0.0.0: esta interface é só pra processos na mesma
VPS (o backend do front-end). O Caddy não deve ter rota apontando pra ela.
"""

from __future__ import annotations

import sys
from pathlib import Path

# garante que `runtime` e `api` sejam importáveis quando rodado como script
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.auth import exigir_api_key  # noqa: E402
from api.config import ErroConfigApi, carregar_config  # noqa: E402
from api.rotas import aprovacoes as rota_aprovacoes  # noqa: E402
from api.rotas import execucoes as rota_execucoes  # noqa: E402
from api.rotas import pecas as rota_pecas  # noqa: E402
from api.rotas import perfil as rota_perfil  # noqa: E402
from api.rotas import posts as rota_posts  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # falha rápida e clara se AGENTE_API_KEY / paths estiverem errados
    carregar_config()
    yield


app = FastAPI(
    title="agente-social-media — casca HTTP interna",
    version="0.1.0",
    description=(
        "Interface estável e interna (127.0.0.1) consumida pelo componente "
        "front-end. Não é a API pública de nada. CLI do agente segue "
        "funcionando à parte."
    ),
    lifespan=lifespan,
)


@app.exception_handler(ErroConfigApi)
async def _erro_config(_request, exc: ErroConfigApi) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"config inválida: {exc}"})


@app.get("/saude", tags=["saude"])
async def saude() -> dict[str, str]:
    """Liveness — não exige chave, não toca em dado nenhum."""
    return {"status": "ok"}


@app.get("/versao", tags=["saude"], dependencies=[Depends(exigir_api_key)])
async def versao() -> dict[str, str]:
    return {"componente": "agente-social-media/api", "versao": app.version}


app.include_router(rota_posts.router)
app.include_router(rota_perfil.router)
app.include_router(rota_aprovacoes.router)
app.include_router(rota_execucoes.router)
app.include_router(rota_pecas.router)


def main() -> None:
    import uvicorn

    config = carregar_config()
    if config.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(
            f"recusando subir em host {config.host!r} — esta casca é só "
            "127.0.0.1 (ver arquitetura.md). Ajuste AGENTE_API_HOST."
        )
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
