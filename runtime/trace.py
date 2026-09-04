"""trace.py — observabilidade (implementa contracts/hooks.md).

Os 5 ganchos de hooks.md viram entradas estruturadas em JSON, gravadas em
dados/trace.json ao final da execução. Extensão documentada em hooks.md:
`antes_da_acao` de uma acao_sensivel (rules.md) vira nível "alerta" em vez
de "log" — é o ponto onde a confirmação humana é exigida (ver executor.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Gancho = Literal["antes_da_etapa", "apos_etapa", "antes_da_acao", "apos_acao", "em_erro"]
Nivel = Literal["log", "alerta"]

# hooks.md: valor padrão de cada gancho.
NIVEL_PADRAO: dict[Gancho, Nivel] = {
    "antes_da_etapa": "log",
    "apos_etapa": "log",
    "antes_da_acao": "log",
    "apos_acao": "log",
    "em_erro": "alerta",
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Trace:
    """Coleciona os eventos de uma execução e persiste em dados/trace.json."""

    execucao_id: str
    caminho_arquivo: Path
    eventos: list[dict[str, Any]] = field(default_factory=list)

    def registrar(
        self,
        gancho: Gancho,
        dados: dict[str, Any],
        *,
        acao_sensivel: bool = False,
    ) -> dict[str, Any]:
        nivel = NIVEL_PADRAO[gancho]
        # extensão de hooks.md: antes_da_acao de acao_sensivel vira alerta
        if gancho == "antes_da_acao" and acao_sensivel:
            nivel = "alerta"
        evento = {
            "execucao_id": self.execucao_id,
            "gancho": gancho,
            "nivel": nivel,
            "timestamp": _agora_iso(),
            "dados": dados,
        }
        self.eventos.append(evento)
        self._persistir()
        return evento

    def antes_da_etapa(self, **dados: Any) -> dict[str, Any]:
        return self.registrar("antes_da_etapa", dados)

    def apos_etapa(self, **dados: Any) -> dict[str, Any]:
        return self.registrar("apos_etapa", dados)

    def antes_da_acao(self, *, acao_sensivel: bool = False, **dados: Any) -> dict[str, Any]:
        return self.registrar("antes_da_acao", dados, acao_sensivel=acao_sensivel)

    def apos_acao(self, **dados: Any) -> dict[str, Any]:
        return self.registrar("apos_acao", dados)

    def em_erro(self, **dados: Any) -> dict[str, Any]:
        return self.registrar("em_erro", dados)

    def _persistir(self) -> None:
        self.caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho_arquivo.open("w", encoding="utf-8") as f:
            json.dump(
                {"execucao_id": self.execucao_id, "eventos": self.eventos},
                f,
                ensure_ascii=False,
                indent=2,
            )


def carregar_trace(caminho_arquivo: Path) -> dict[str, Any] | None:
    """Usado pelo comando `rastreamento` pra ler a última execução."""
    if not caminho_arquivo.exists():
        return None
    with caminho_arquivo.open("r", encoding="utf-8") as f:
        return json.load(f)
