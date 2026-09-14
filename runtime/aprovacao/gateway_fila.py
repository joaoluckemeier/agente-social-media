"""runtime/aprovacao/gateway_fila.py — gateway assíncrono (fila de aprovação).

Não pergunta nada na hora: consulta a tabela `aprovacoes` (via
`MemoriaRepository`) por uma decisão já registrada para a pendência atual
`(execucao_id, etapa, chave_peca)`.
  - decisão encontrada  -> devolve {aprovado, feedback} e o ciclo segue;
  - sem decisão         -> grava a pendência e levanta RunSuspensa.

A decisão em si chega pela casca HTTP (`POST /aprovacoes/{id}/decidir`), que
só grava a linha — quem consome e valida é o loop do próprio agente ao ser
retomado.
"""

from __future__ import annotations

from typing import Any

from ..memoria import MemoriaRepository
from .base import GatewayAprovacao, RunSuspensa, chave_peca


class GatewayAprovacaoFila(GatewayAprovacao):
    def __init__(self, memoria: MemoriaRepository):
        self._memoria = memoria

    def _resolver(self, *, execucao_id: str, peca: dict[str, Any], etapa: str) -> dict[str, Any]:
        chave = chave_peca(peca)
        registro = self._memoria.buscar_aprovacao(execucao_id, etapa, chave)
        if registro is not None and registro["estado"] == "decidida":
            return {
                "aprovado": bool(registro["aprovado"]),
                "feedback": registro.get("feedback") or "",
            }
        aprovacao_id = self._memoria.registrar_aprovacao_pendente(
            execucao_id=execucao_id, etapa=etapa, chave_peca=chave, peca=peca
        )
        raise RunSuspensa(execucao_id=execucao_id, etapa=etapa, aprovacao_id=aprovacao_id)

    def solicitar_aprovacao(
        self, *, execucao_id: str, peca: dict[str, Any], etapa: str
    ) -> dict[str, Any]:
        return self._resolver(execucao_id=execucao_id, peca=peca, etapa=etapa)

    def confirmar_acao_sensivel(
        self, *, execucao_id: str, nome_ferramenta: str, argumentos: dict[str, Any]
    ) -> bool:
        decisao = self._resolver(
            execucao_id=execucao_id,
            peca={"ferramenta": nome_ferramenta, "argumentos": argumentos},
            etapa="publicacao",
        )
        return bool(decisao["aprovado"])
