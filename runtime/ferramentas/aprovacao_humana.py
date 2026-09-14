"""ferramentas/aprovacao_humana.py — skills.md: solicitar_aprovacao_humana.

Apresenta uma peça (roteiro ou visual) pro usuário e aguarda decisão, peça
por peça — nunca em lote (rules.md).

A apresentação/decisão em si vive no `GatewayAprovacao` injetado pelo
executor (runtime/aprovacao/):
  - `GatewayAprovacaoCLI`  — prompt síncrono no terminal (comportamento de
    sempre; é o default);
  - `GatewayAprovacaoFila` — grava a pendência e suspende a execução até a
    decisão chegar pela casca HTTP.

Distinto da confirmação de `acao_sensivel` de `publicar_conteudo` (essa
também passa pelo gateway, mas é chamada direto pelo executor).
"""

from __future__ import annotations

from typing import Any

from ..aprovacao import GatewayAprovacao
from ..aprovacao.gateway_cli import GatewayAprovacaoCLI


def solicitar_aprovacao_humana(
    *,
    peca: dict[str, Any],
    etapa: str,
    gateway: GatewayAprovacao | None = None,
    execucao_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """entrada: {peca, etapa} · saida: {aprovado: bool, feedback: string}.

    Pode levantar RunSuspensa quando o gateway é o de fila e ainda não há
    decisão registrada — o executor não a trata como erro (ver
    executor._chamar_com_retry) e ciclo.executar_ciclo suspende a execução.
    """
    gateway = gateway or GatewayAprovacaoCLI()
    return gateway.solicitar_aprovacao(execucao_id=execucao_id or "", peca=peca, etapa=etapa)
