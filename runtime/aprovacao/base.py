"""runtime/aprovacao/base.py — interface do gateway de aprovação + RunSuspensa."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any


class RunSuspensa(Exception):
    """Levantada pelo `GatewayAprovacaoFila` quando não há decisão registrada
    para a pendência atual. `ciclo.executar_ciclo` a propaga (depois de
    anexar `segundos_ativos`); quem orquestra (o worker da casca HTTP)
    persiste o estado 'suspensa' e responde. O CLI nunca vê isso — o gateway
    dele é síncrono.
    """

    def __init__(self, *, execucao_id: str, etapa: str, aprovacao_id: str):
        self.execucao_id = execucao_id
        self.etapa = etapa
        self.aprovacao_id = aprovacao_id
        # preenchido por ciclo.executar_ciclo antes de re-propagar
        self.segundos_ativos: float = 0.0
        super().__init__(
            f"execução {execucao_id} suspensa aguardando aprovação de '{etapa}' "
            f"(aprovacao {aprovacao_id})"
        )


def chave_peca(peca: dict[str, Any]) -> str:
    """Hash estável do conteúdo submetido à aprovação. Distingue 'aprovação do
    roteiro v1' de 'aprovação do roteiro v2' (após uma reprovação + nova
    geração) — o planejador já usa o mesmo critério (roteiro_texto /
    pecas_urls) pra saber se a aprovação registrada é da versão atual."""
    bruto = json.dumps(peca, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


class GatewayAprovacao(ABC):
    """Como o runtime pede uma decisão humana. Duas etapas de aprovação de
    conteúdo (`roteiro`, `visual`) e a confirmação de ação sensível
    (`publicacao`) passam por aqui."""

    @abstractmethod
    def solicitar_aprovacao(
        self, *, execucao_id: str, peca: dict[str, Any], etapa: str
    ) -> dict[str, Any]:
        """etapa ∈ {'roteiro','visual'} · retorna {aprovado: bool, feedback: str}.
        Pode levantar RunSuspensa (gateway de fila)."""

    @abstractmethod
    def confirmar_acao_sensivel(
        self, *, execucao_id: str, nome_ferramenta: str, argumentos: dict[str, Any]
    ) -> bool:
        """Gate de `rules.md: acoes_sensiveis` (hoje só `publicar_conteudo`).
        Retorna True/False. Pode levantar RunSuspensa (gateway de fila)."""
