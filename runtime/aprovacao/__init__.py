"""runtime/aprovacao/ — o gateway de aprovação humana.

O passo de aprovação (roteiro/visual) e a confirmação de `acao_sensivel`
(`publicar_conteudo`) deixam de ser um `input()` fixo no meio do ciclo e
passam por um `GatewayAprovacao` injetável:

  - `GatewayAprovacaoCLI`  — comportamento síncrono de sempre (prompt no
    terminal). É o default; o CLI (`comando rodar`) não muda em nada.
  - `GatewayAprovacaoFila` — grava a pendência no banco (tabela `aprovacoes`
    via `MemoriaRepository`) e SUSPENDE a execução (`RunSuspensa`). Quando a
    decisão chega (pela casca HTTP), a execução é retomada e o planejador —
    que já reconstrói todo o estado a partir de `memoria_curta` — segue do
    ponto exato, sem caminho paralelo de validação.

Isso é o que `rules.md` antecipa ("O contrato já está pronto para o dia em
que a política mudar") e `decisoes-de-engenharia.md` §11.
"""

from __future__ import annotations

from .base import GatewayAprovacao, RunSuspensa

__all__ = ["GatewayAprovacao", "RunSuspensa"]
