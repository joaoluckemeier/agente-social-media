"""api/observabilidade.py — registro de quem chamou a casca HTTP, quando, e
que a origem foi a API (não o CLI).

Reusa o formato de evento estruturado de runtime/trace.py (gancho, nivel,
timestamp, dados), mas grava num arquivo separado append-only
(`dados/trace-api.jsonl`) pra não sobrescrever o `trace.json` da última
execução — esse continua sendo responsabilidade do runtime.Trace.

Quando uma ação da API dispara/retoma um ciclo (Etapa 2), o runtime.Trace
daquela execução registra os passos normalmente; aqui fica só o ponto de
entrada: rota, método, chamador, resultado.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import carregar_config

# mesma ideia de níveis de hooks.md: "log" é o padrão, "alerta" é exceção.
_NIVEL_PADRAO = "log"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _caminho_log() -> Path:
    return carregar_config().trace_path.parent / "trace-api.jsonl"


def registrar_evento_api(
    *,
    rota: str,
    metodo: str,
    chamador: str,
    resultado: str,
    nivel: str = _NIVEL_PADRAO,
    execucao_id: str | None = None,
    detalhes: dict[str, Any] | None = None,
) -> None:
    evento = {
        "origem": "api",
        "gancho": "chamada_api",
        "nivel": nivel,
        "timestamp": _agora_iso(),
        "chamador": chamador,
        "rota": rota,
        "metodo": metodo,
        "resultado": resultado,
        "execucao_id": execucao_id,
        "dados": detalhes or {},
    }
    caminho = _caminho_log()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
