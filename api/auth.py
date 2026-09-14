"""api/auth.py — autenticação da casca HTTP: chave compartilhada simples.

Não é JWT (arquitetura.md): é conexão máquina-a-máquina com um único
chamador confiável (o backend do front-end). Todo request precisa trazer
o header `X-API-Key` igual a `AGENTE_API_KEY`. Comparação em tempo
constante pra não vazar a chave por timing.

O header `X-Chamador` (opcional, livre) é registrado no trace junto com a
origem — é só rótulo de observabilidade, nunca base de autorização.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import ConfigApi, carregar_config


def _extrair_chave(x_api_key: str | None) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="header X-API-Key ausente",
        )
    return x_api_key


async def exigir_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    config: ConfigApi = Depends(carregar_config),
) -> None:
    chave = _extrair_chave(x_api_key)
    if not hmac.compare_digest(chave, config.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key inválida",
        )


async def identificar_chamador(
    x_chamador: str | None = Header(default=None, alias="X-Chamador"),
) -> str:
    """Rótulo livre de quem chamou (ex: 'front-end', 'front-end:tenant-1').
    Só observabilidade — ver api/observabilidade.py."""
    return (x_chamador or "desconhecido").strip()[:120] or "desconhecido"
