"""adapters/fotos_estoque/base_adapter.py — interface Adapter.

decisoes-de-engenharia.md, seção 2: o motor de template nunca fala com a API
de um banco de fotos diretamente — fala com esta interface. v1:
UnsplashAdapter. Trocar de fonte (Pexels/outro) é implementar esta interface
de novo, sem tocar em geracao_visual/imagem/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Foto:
    dados: bytes
    mime: str
    credito: str  # atribuição exigida pela licença (ex: "Foto de Fulano / Unsplash")
    origem_url: str


class FotoEstoqueAdapter(ABC):
    @abstractmethod
    def buscar_foto(self, query: str, *, orientacao: str = "portrait", pular: int = 0) -> Foto:
        """Busca uma foto real e licenciada para `query` e devolve os bytes
        já baixados. `orientacao`: portrait | landscape | squarish. `pular`:
        quantos resultados iniciais ignorar (regeneração pede uma foto
        diferente da anterior).

        Levanta ErroConfiguracaoAusente se faltar credencial, e RuntimeError
        se a busca não retornar nenhuma foto utilizável."""
        raise NotImplementedError
