"""api/guardas.py — proteções de POST /execucoes na casca do agente.

2ª camada (a 1ª é no backend do front-end):
  - trava de execução concorrente: nunca duas execuções ao mesmo tempo
    contra o mesmo SQLite (1 instância = 1 tenant);
  - rate limit local por janela (hora/dia) — POST /execucoes custa dinheiro
    real (LLM e, sobretudo, vídeo via Veo).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runtime.memoria import MemoriaRepository

from .config import ConfigApi


class ExecucaoEmAndamento(Exception):
    """Já existe execução ativa/suspensa — 409."""

    def __init__(self, execucao_id: str, estado: str):
        self.execucao_id = execucao_id
        self.estado = estado
        super().__init__(f"execução {execucao_id} está '{estado}'")


class RateLimitLocalAtingido(Exception):
    """Teto de disparos por janela — 429."""

    def __init__(self, janela: str, limite: int):
        self.janela = janela
        self.limite = limite
        super().__init__(f"limite de execuções por {janela} atingido ({limite})")


def checar_pode_disparar(memoria: MemoriaRepository, config: ConfigApi) -> None:
    andamento = memoria.execucao_em_andamento()
    if andamento is not None:
        raise ExecucaoEmAndamento(andamento["execucao_id"], andamento["estado"])

    agora = datetime.now(timezone.utc)
    for janela, delta, limite in (
        ("hora", timedelta(hours=1), config.exec_max_por_hora),
        ("dia", timedelta(days=1), config.exec_max_por_dia),
    ):
        usados = memoria.contar_disparos_desde((agora - delta).isoformat())
        if usados >= limite:
            raise RateLimitLocalAtingido(janela, limite)
