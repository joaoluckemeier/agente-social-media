"""api/config.py — configuração da casca HTTP, lida do ambiente (.env do
agente, mesmo arquivo que o CLI já usa via runtime.cli._carregar_env).

Nada aqui é segredo de negócio (isso vive em perfil-marca.md) — só chave
de acesso máquina-a-máquina e caminhos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# raiz do agente = pai da pasta api/
AGENTE_DIR = Path(__file__).resolve().parent.parent


class ErroConfigApi(RuntimeError):
    """Configuração obrigatória da API ausente ou inválida."""


@dataclass(frozen=True)
class ConfigApi:
    api_key: str
    db_path: Path
    perfil_path: Path
    trace_path: Path
    host: str
    port: int
    # rate limit local (2ª camada — a 1ª é no backend do front-end).
    exec_max_por_hora: int
    exec_max_por_dia: int

    @property
    def agente_dir(self) -> Path:
        return AGENTE_DIR


def _int_env(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome, "").strip()
    if not valor:
        return padrao
    try:
        return int(valor)
    except ValueError as exc:
        raise ErroConfigApi(f"{nome} precisa ser inteiro, recebi {valor!r}") from exc


@lru_cache(maxsize=1)
def carregar_config() -> ConfigApi:
    caminho_env = AGENTE_DIR / ".env"
    if caminho_env.exists():
        load_dotenv(caminho_env)
    else:
        load_dotenv()

    api_key = os.environ.get("AGENTE_API_KEY", "").strip()
    if not api_key:
        raise ErroConfigApi(
            "AGENTE_API_KEY ausente no .env — a casca HTTP não sobe sem chave "
            "de acesso (arquitetura.md: 'autenticação por chave compartilhada "
            "verificada em todo request')."
        )
    if len(api_key) < 16:
        raise ErroConfigApi("AGENTE_API_KEY curta demais (mínimo 16 caracteres).")

    db_path = Path(
        os.environ.get("DATABASE_PATH") or (AGENTE_DIR / "dados" / "agente.db")
    )
    # mesmo default que comandos.md/config-exemplo: o perfil real que o
    # runtime consome via --perfil. O front-end atualiza este arquivo através
    # de PUT /perfil (nunca escrevendo nele por fora).
    perfil_path = Path(
        os.environ.get("PERFIL_PATH")
        or (AGENTE_DIR / "config-exemplo" / "perfil-marca.md")
    )
    trace_path = AGENTE_DIR / "dados" / "trace.json"

    return ConfigApi(
        api_key=api_key,
        db_path=db_path,
        perfil_path=perfil_path,
        trace_path=trace_path,
        host=os.environ.get("AGENTE_API_HOST", "127.0.0.1"),
        port=_int_env("AGENTE_API_PORT", 8790),
        exec_max_por_hora=_int_env("EXEC_MAX_POR_HORA", 2),
        exec_max_por_dia=_int_env("EXEC_MAX_POR_DIA", 8),
    )
