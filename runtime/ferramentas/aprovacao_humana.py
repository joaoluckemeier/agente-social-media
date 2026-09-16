"""ferramentas/aprovacao_humana.py — skills.md: solicitar_aprovacao_humana.

Apresenta uma peça (roteiro ou visual) pro usuário e aguarda decisão, peça
por peça — nunca em lote (rules.md). v1: prompt síncrono no CLI. Distinto da
confirmação de acao_sensivel de publicar_conteudo (essa vive em
executor.py, ver rules.md/hooks.md) — aqui é a aprovação de conteúdo em si.
"""

from __future__ import annotations

from typing import Any


def _mostrar_peca(peca: dict[str, Any], etapa: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"APROVAÇÃO — etapa: {etapa}")
    print("=" * 60)
    nota = (peca.get("nota") or "").strip()
    if nota:
        # extensão — não é do contrato de skills.md (`peca: object` é livre):
        # aviso do planejador quando não há mais orçamento de regeneração
        # automática (rules.md: chamadas_ferramenta) pra essa etapa.
        print(f"[NOTA] {nota}\n")
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


def solicitar_aprovacao_humana(*, peca: dict[str, Any], etapa: str, **_: Any) -> dict[str, Any]:
    """entrada: {peca, etapa} · saida: {aprovado: bool, feedback: string}"""
    _mostrar_peca(peca, etapa)
    resposta = input("Aprovar? [s/N]: ").strip().lower()
    aprovado = resposta in ("s", "sim", "y", "yes")
    feedback = ""
    if not aprovado:
        feedback = input("O que precisa mudar? (Enter pra deixar em branco): ").strip()
    return {"aprovado": aprovado, "feedback": feedback}
