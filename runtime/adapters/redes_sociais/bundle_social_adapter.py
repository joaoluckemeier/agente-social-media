"""adapters/redes_sociais/bundle_social_adapter.py — implementação v1.

Fala com a API unificada de publicação multi-rede bundle.social
(BUNDLE_SOCIAL_API_KEY, BUNDLE_SOCIAL_ACCOUNT_ID_INSTAGRAM), em vez da Graph
API do Meta diretamente (decisoes-de-engenharia.md, seção 2). v1 publica só
no Instagram (rules.md).

ATENÇÃO — maior incerteza deste plano: não tenho a documentação oficial da
bundle.social em mãos com certeza suficiente pra garantir que o endpoint e
o formato de payload abaixo batem exatamente com a API real hoje. Isolei
tudo o que é "forma da requisição" em `_endpoint_criar_post` e
`_montar_payload` — quando a BUNDLE_SOCIAL_API_KEY real estiver configurada,
validar essas duas partes contra https://docs.bundle.social (ou a doc
vigente) antes do primeiro uso em produção; o resto do adapter (interface,
upload do arquivo local, tratamento de resposta/erro) não deve precisar
mudar.

Cada item de `pecas_urls` aqui, na prática, é um caminho local gerado por
gerar_peca_visual (ver geracao_visual/base_estrategia.py) — este adapter faz
upload direto dos arquivos, não assume URL pública. Carrossel de verdade
(decisão revista em skills.md): pode vir mais de um caminho, na ordem em
que devem aparecer no post.
"""

from __future__ import annotations


import os
from pathlib import Path
from typing import Any

import requests

from .base_adapter import RedeSocialAdapter
from ... import ErroConfiguracaoAusente

_TIMEOUT_REQUISICAO_SEGUNDOS = 30


def _base_url() -> str:
    return os.environ.get("BUNDLE_SOCIAL_API_BASE_URL") or "https://api.bundle.social"


def _conta_id_para_rede(rede: str) -> str:
    # v1 só publica no Instagram (rules.md) — mapear outra rede aqui é o
    # único ponto a mexer pra adicionar TikTok/LinkedIn no futuro (OCP).
    if rede != "instagram":
        raise ValueError(f"BundleSocialAdapter: rede não suportada na v1: {rede!r}")
    conta_id = os.environ.get("BUNDLE_SOCIAL_ACCOUNT_ID_INSTAGRAM")
    if not conta_id:
        raise ErroConfiguracaoAusente("BUNDLE_SOCIAL_ACCOUNT_ID_INSTAGRAM não configurado no .env.")
    return conta_id


class BundleSocialAdapter(RedeSocialAdapter):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def _api_key_resolvida(self) -> str:
        chave = self._api_key or os.environ.get("BUNDLE_SOCIAL_API_KEY")
        if not chave:
            raise ErroConfiguracaoAusente("BUNDLE_SOCIAL_API_KEY não configurado no .env.")
        return chave

    def _endpoint_criar_post(self) -> str:
        return f"{_base_url()}/api/v1/posts"

    def _montar_payload(self, *, conta_id: str, legenda: str) -> dict[str, Any]:
        return {"accountId": conta_id, "caption": legenda, "publishImmediately": True}

    def publicar(self, *, pecas_urls: list[str], rede: str, legenda: str) -> dict[str, Any]:
        conta_id = _conta_id_para_rede(rede)
        cabecalhos = {"Authorization": f"Bearer {self._api_key_resolvida()}"}
        payload = self._montar_payload(conta_id=conta_id, legenda=legenda)

        caminhos = [Path(p) for p in pecas_urls]
        for caminho in caminhos:
            if not caminho.exists():
                raise FileNotFoundError(f"BundleSocialAdapter: peça não encontrada em {caminho!r}")

        # ATENÇÃO — mesma incerteza documentada no topo do arquivo: várias
        # APIs unificadas aceitam múltiplos arquivos num só campo "media[]"
        # (multipart) pra montar carrossel; não confirmado contra a doc real
        # da bundle.social. É o outro ponto a ajustar aqui, junto com
        # _endpoint_criar_post/_montar_payload, quando a integração real
        # acontecer.
        arquivos_abertos = [caminho.open("rb") for caminho in caminhos]
        try:
            resposta = requests.post(
                self._endpoint_criar_post(),
                headers=cabecalhos,
                data=payload,
                files=[("media[]", (c.name, f)) for c, f in zip(caminhos, arquivos_abertos)],
                timeout=_TIMEOUT_REQUISICAO_SEGUNDOS,
            )
        finally:
            for f in arquivos_abertos:
                f.close()
        resposta.raise_for_status()  # não-2xx levanta requests.HTTPError
        dados = resposta.json()

        # publishImmediately=True no payload + 2xx aqui = publicado agora.
        # Não repassamos o status bruto da API (provavelmente em inglês,
        # ex: "published"/"queued") direto pro contrato — planejador.py
        # compara literalmente com a string "publicado" (rules.md/planner.md
        # tratam isso como o valor que sinaliza sucesso), então normalizamos
        # aqui em vez de criar um vocabulário divergente por fora do adapter.
        return {
            "post_id": dados.get("id") or dados.get("postId", ""),
            "status": "publicado",
            "publicado_em": dados.get("publishedAt", ""),
        }
