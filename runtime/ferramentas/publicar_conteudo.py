"""ferramentas/publicar_conteudo.py — skills.md: publicar_conteudo.

Publica a(s) peça(s) aprovada(s) via RedeSocialAdapter (v1: BundleSocialAdapter).
AÇÃO SENSÍVEL (rules.md) — a confirmação humana síncrona já foi aplicada
pelo executor.py antes de chamar esta função; esta função não pergunta nada
de novo, só executa.

Decisão revista (skills.md): `peca_url: string` virou `pecas_urls: list` —
carrossel de verdade publica várias imagens num post só.
"""

from __future__ import annotations

from typing import Any

from ..adapters.redes_sociais.base_adapter import RedeSocialAdapter
from ..adapters.redes_sociais.bundle_social_adapter import BundleSocialAdapter

_ADAPTER_PADRAO: RedeSocialAdapter = BundleSocialAdapter()


def publicar_conteudo(
    *, pecas_urls: list[str], rede: str, legenda: str, adapter: RedeSocialAdapter | None = None, **_: Any
) -> dict[str, Any]:
    """entrada: {pecas_urls, rede, legenda} · saida: {post_id, status, publicado_em}"""
    adapter = adapter or _ADAPTER_PADRAO
    return adapter.publicar(pecas_urls=pecas_urls, rede=rede, legenda=legenda)
