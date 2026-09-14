"""runtime/aprovacao/gateway_cli.py — o gateway síncrono de sempre.

Contém, sem mudança de comportamento, o que antes vivia em
`ferramentas/aprovacao_humana.py` (prompt de aprovação de conteúdo) e em
`executor._confirmar_acao_sensivel` (confirmação de ação sensível). O
`comando rodar` do CLI usa este gateway — os prompts `[s/N]` continuam
idênticos.
"""

from __future__ import annotations

from typing import Any

from .base import GatewayAprovacao


def _mostrar_peca(peca: dict[str, Any], etapa: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"APROVAÇÃO — etapa: {etapa}")
    print("=" * 60)
    if etapa == "roteiro":
        print(f"Tema: {peca.get('tema', '')}")
        print(f"Formato: {peca.get('formato', '')}")
        slides = peca.get("slides") or []
        print(f"\nRoteiro — {len(slides)} slide(s):\n")
        for s in slides:
            print(f"[{s.get('ordem', '?')}] ({s.get('tipo_layout', '?')}) {s.get('titulo', '')}")
            corpo = (s.get("corpo") or "").strip()
            if corpo:
                for linha in corpo.splitlines():
                    print(f"      {linha}")
            consulta = (s.get("consulta_foto") or "").strip()
            if consulta:
                print(f"      [foto: {consulta}]")
            print()
    elif etapa == "visual":
        pecas_urls = peca.get("pecas_urls") or []
        print(f"Formato: {peca.get('formato', '')}")
        print(f"{len(pecas_urls)} peça(s):")
        for i, url in enumerate(pecas_urls, start=1):
            print(f"  [{i}] {url}")
    else:
        for chave, valor in peca.items():
            print(f"{chave}: {valor}")
    print("=" * 60)


class GatewayAprovacaoCLI(GatewayAprovacao):
    def solicitar_aprovacao(
        self, *, execucao_id: str, peca: dict[str, Any], etapa: str
    ) -> dict[str, Any]:
        _mostrar_peca(peca, etapa)
        resposta = input("Aprovar? [s/N]: ").strip().lower()
        aprovado = resposta in ("s", "sim", "y", "yes")
        feedback = ""
        if not aprovado:
            feedback = input("O que precisa mudar? (Enter pra deixar em branco): ").strip()
        return {"aprovado": aprovado, "feedback": feedback}

    def confirmar_acao_sensivel(
        self, *, execucao_id: str, nome_ferramenta: str, argumentos: dict[str, Any]
    ) -> bool:
        print("\n[CONFIRMAÇÃO NECESSÁRIA — ação sensível]")
        print(f"  ferramenta: {nome_ferramenta}")
        for chave, valor in argumentos.items():
            print(f"  {chave}: {valor}")
        resposta = input("Confirmar execução? [s/N]: ").strip().lower()
        return resposta in ("s", "sim", "y", "yes")
