"""adapters/redes_sociais/base_adapter.py — interface Adapter.

decisoes-de-engenharia.md, seção 2: publicar_conteudo nunca fala com a API
nativa de uma rede diretamente — fala com esta interface. v1:
BundleSocialAdapter (API unificada multi-rede). Adicionar TikTok/LinkedIn no
futuro é trocar a configuração da conta conectada, sem tocar em
planejador.py/ciclo.py/executor.py (OCP).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RedeSocialAdapter(ABC):
    @abstractmethod
    def publicar(self, *, pecas_urls: list[str], rede: str, legenda: str) -> dict[str, Any]:
        """Retorna {"post_id": str, "status": str, "publicado_em": str}.

        `pecas_urls` (decisão revista — skills.md): 1 ou mais peças, na
        ordem em que devem aparecer no post (carrossel de verdade)."""
        raise NotImplementedError
