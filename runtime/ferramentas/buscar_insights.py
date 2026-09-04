"""ferramentas/buscar_insights.py — skills.md: buscar_insights_recentes.

Lê a tabela `insights` (escrita pelo agente-analista-metricas) via
MemoriaRepository — não é chamada de API externa, é leitura de repositório
(skills.md é explícito sobre isso).
"""

from __future__ import annotations

from typing import Any

from ..memoria import MemoriaRepository


def buscar_insights_recentes(*, limite: int, memoria: MemoriaRepository, **_: Any) -> dict[str, Any]:
    """entrada: {limite: int} · saida: {insights: list}"""
    insights = memoria.buscar_insights_recentes(limite)
    return {"insights": insights}
