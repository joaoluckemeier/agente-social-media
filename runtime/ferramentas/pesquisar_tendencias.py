"""ferramentas/pesquisar_tendencias.py — skills.md: pesquisar_tendencias_nicho.

Busca temas/formatos em alta no nicho, na rede indicada. A fonte dos dados
fica atrás de uma interface (`FonteTendencias`) — decisão explícita: v1 usa
só a OpenAI (síntese a partir do conhecimento do modelo + raciocínio sobre o
ICP), sem busca web ao vivo, pra não introduzir uma credencial/dependência
nova agora. Trocar de fonte no futuro (ex: uma API de busca real) é
implementar `FonteTendencias` de novo e trocar `_FONTE_PADRAO` — não toca
em mais nada (mesmo espírito de Strategy usado em geracao_visual/).

Cache: decisoes-de-engenharia.md, seção 4 — só esta ferramenta se beneficia
de cache, "curto" (6h), porque tendência de nicho não muda de hora em hora.
"""

from __future__ import annotations


import json
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from ..memoria import MemoriaRepository
from .. import ErroConfiguracaoAusente

CACHE_TTL_SEGUNDOS = 6 * 60 * 60  # decisoes-de-engenharia.md, seção 4: "ex: 6h"


def _chave_openai() -> str:
    chave = os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise ErroConfiguracaoAusente(
            "OPENAI_API_KEY não configurado no .env (ver .env.example) — "
            "necessário para chamadas à OpenAI."
        )
    return chave


class FonteTendencias(ABC):
    @abstractmethod
    def buscar(self, *, nicho: str, rede: str) -> dict[str, Any]:
        """Retorna {"tendencias": list, "temas_sugeridos": list}."""
        raise NotImplementedError


_SYSTEM_PROMPT = """\
Você pesquisa tendências de conteúdo pra redes sociais no nicho informado. \
Como você não tem acesso a busca ao vivo, baseie-se no seu conhecimento \
geral de formatos e ganchos que costumam performar bem nesse tipo de nicho \
B2B (donos de loja física, dor de atendimento/operação) na rede indicada, \
priorizando o que é acionável pra um post que ainda vai ser roteirizado.

Responda SOMENTE em JSON, no formato exato:
{"tendencias": ["<tendência ou formato em alta 1>", ...],
 "temas_sugeridos": ["<tema concreto de post 1>", ...]}\
"""


class FonteTendenciasOpenAI(FonteTendencias):
    def __init__(self, modelo: str | None = None):
        self._modelo = modelo

    def _modelo_resolvido(self) -> str:
        modelo = self._modelo or os.environ.get("OPENAI_MODEL_ROTEIRO")
        if not modelo:
            raise ErroConfiguracaoAusente(
                "OPENAI_MODEL_ROTEIRO não configurado no .env — "
                "pesquisar_tendencias_nicho reaproveita esse modelo por padrão."
            )
        return modelo

    def buscar(self, *, nicho: str, rede: str) -> dict[str, Any]:
        cliente = OpenAI(api_key=_chave_openai())
        resposta = cliente.chat.completions.create(
            model=self._modelo_resolvido(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"nicho": nicho, "rede": rede}, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
        )
        dados = json.loads(resposta.choices[0].message.content)
        return {
            "tendencias": dados.get("tendencias", []),
            "temas_sugeridos": dados.get("temas_sugeridos", []),
        }


_FONTE_PADRAO: FonteTendencias = FonteTendenciasOpenAI()


def pesquisar_tendencias_nicho(
    *, nicho: str, rede: str, memoria: MemoriaRepository, fonte: FonteTendencias | None = None, **_: Any
) -> dict[str, Any]:
    """entrada: {nicho: string, rede: string} · saida: {tendencias: list, temas_sugeridos: list}"""
    fonte = fonte or _FONTE_PADRAO
    chave_cache = f"tendencias:{nicho}:{rede}"

    em_cache = memoria.obter_cache(chave_cache)
    if em_cache is not None:
        return em_cache

    resultado = fonte.buscar(nicho=nicho, rede=rede)
    memoria.salvar_cache(chave_cache, resultado, ttl_segundos=CACHE_TTL_SEGUNDOS)
    return resultado
