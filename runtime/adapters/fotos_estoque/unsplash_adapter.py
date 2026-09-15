"""adapters/fotos_estoque/unsplash_adapter.py — implementação v1.

Unsplash API (`UNSPLASH_ACCESS_KEY`, gratuita mas ainda uma credencial —
vai no .env como as demais, decisoes-de-engenharia.md seção 5). Busca uma
foto relevante para a query, dispara o endpoint de "download" exigido pelas
diretrizes da API (best-effort) e baixa os bytes.

Fallback: se a query vier com 0 resultados (ex: `gerar_roteiro` gerou uma
`consulta_foto` específica demais), tenta de novo com só as 2 primeiras
palavras antes de desistir — evita quebrar o ciclo inteiro por uma busca
malformada.

Timeout/retry de rede ficam a cargo de executor.py.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from ... import ErroConfiguracaoAusente
from .base_adapter import Foto, FotoEstoqueAdapter

_BUSCA_URL = "https://api.unsplash.com/search/photos"
_TIMEOUT_SEGUNDOS = 20
# largura pedida ao CDN da Unsplash (o `raw` aceita params de redimensionamento)
_LARGURA_ALVO = 1400


def _simplificar(query: str) -> str:
    """Versão mais genérica da query: só as 2 primeiras palavras."""
    return " ".join(query.split()[:2])


class UnsplashAdapter(FotoEstoqueAdapter):
    def __init__(self, access_key: str | None = None):
        self._access_key = access_key

    def _chave(self) -> str:
        chave = self._access_key or os.environ.get("UNSPLASH_ACCESS_KEY")
        if not chave:
            raise ErroConfiguracaoAusente(
                "UNSPLASH_ACCESS_KEY não configurado no .env (ver .env.example) — "
                "necessário para os templates que pedem foto real (foto_split, "
                "capa com imagem)."
            )
        return chave

    def _buscar_resultados(
        self, cabecalhos: dict[str, str], query: str, orientacao: str, per_page: int
    ) -> list[dict[str, Any]]:
        resposta = requests.get(
            _BUSCA_URL,
            headers=cabecalhos,
            params={
                "query": query,
                "per_page": per_page,
                "orientation": orientacao,
                "content_filter": "high",
            },
            timeout=_TIMEOUT_SEGUNDOS,
        )
        resposta.raise_for_status()
        return (resposta.json() or {}).get("results") or []

    def buscar_foto(self, query: str, *, orientacao: str = "portrait", pular: int = 0, ids_evitar: set[str] | None = None,) -> Foto:
        cabecalhos = {"Authorization": f"Client-ID {self._chave()}", "Accept-Version": "v1"}
        pular = max(0, int(pular))
        ids_evitar = ids_evitar or set()
        # pede mais resultados quando há IDs pra evitar, pra ter de onde escolher
        per_page = min(pular + 1 + len(ids_evitar), 10)

        query = (query or "").strip()
        tentativas = [query]
        simples = _simplificar(query)
        if simples and simples.lower() != query.lower():
            tentativas.append(simples)

        resultados: list[dict[str, Any]] = []
        usada = query
        for candidata in tentativas:
            resultados = self._buscar_resultados(cabecalhos, candidata, orientacao, per_page)
            if resultados:
                usada = candidata
                break

        if not resultados:
            raise RuntimeError(
                f"UnsplashAdapter: nenhuma foto encontrada para {query!r} "
                f"(nem para a versão simplificada {simples!r})."
            )

        candidatos = [r for r in resultados if r.get("id") not in ids_evitar] or resultados
        foto = candidatos[min(pular, len(candidatos) - 1)]
        urls = foto.get("urls") or {}
        url_imagem = urls.get("raw") or urls.get("regular") or urls.get("full")
        if not url_imagem:
            raise RuntimeError(f"UnsplashAdapter: resultado sem URL de imagem para {usada!r}.")
        if "raw" in urls and url_imagem == urls["raw"]:
            sep = "&" if "?" in url_imagem else "?"
            url_imagem = f"{url_imagem}{sep}w={_LARGURA_ALVO}&fit=crop&q=80"

        # diretriz da API da Unsplash: registrar o download antes de usar.
        download_location = (foto.get("links") or {}).get("download_location")
        if download_location:
            try:
                requests.get(download_location, headers=cabecalhos, timeout=_TIMEOUT_SEGUNDOS)
            except requests.RequestException:
                pass  # best-effort — não impede o uso da foto

        img = requests.get(url_imagem, timeout=_TIMEOUT_SEGUNDOS)
        img.raise_for_status()

        autor = ((foto.get("user") or {}).get("name")) or "Unsplash"
        return Foto(
            dados=img.content,
            mime=img.headers.get("Content-Type", "image/jpeg").split(";")[0].strip(),
            credito=f"Foto de {autor} / Unsplash",
            origem_url=(foto.get("links") or {}).get("html", url_imagem),
            foto_id=foto.get("id"),
        )
