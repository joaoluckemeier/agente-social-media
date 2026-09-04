"""geracao_visual/video/base_veo.py — base compartilhada das estratégias de
vídeo (Veo).

Contém a chamada assíncrona ao Veo (`generate_videos` + polling + download)
— migrada sem mudança de comportamento do antigo
`geracao_visual/estrategia_video_gemini.py`. As subclasses só dizem QUAL
modelo do Veo chamar e o custo por segundo do tier.

ATENÇÃO: geração de vídeo via Veo é assíncrona (operação de longa duração,
com polling) — o padrão abaixo é o documentado no momento desta
implementação. Validar contra a versão instalada do `google-genai` antes do
primeiro uso em produção. Nomes de modelo do Veo mudam com frequência —
confirmar o ID atual na documentação do Gemini.

Timeout (120s) é aplicado por executor.py (via ThreadPoolExecutor) — o
polling aqui dentro só precisa ser interrompível.
"""

from __future__ import annotations

import os
import time
from typing import Any

from google import genai
from google.genai import types

from ... import ErroConfiguracaoAusente
from ..base_estrategia import EstrategiaGeracaoVisual, salvar_peca_localmente

_ESTILO_MARCA = (
    "Estilo visual: vídeo curto e direto pra Reels do Instagram, tom "
    "consultivo (não hype de IA), cenário de loja de móveis/marcenaria no "
    "Brasil — nunca clipart genérico de IA/robô."
)

_INTERVALO_POLLING_SEGUNDOS = 5


def _chave_gemini() -> str:
    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        raise ErroConfiguracaoAusente(
            "GEMINI_API_KEY não configurado no .env (ver .env.example) — "
            "necessário para geração de vídeo (reel) via Veo."
        )
    return chave


def _prompt_video(roteiro: str) -> str:
    return f"Roteiro do reel (gancho, desenvolvimento, CTA):\n\n{roteiro}\n\n{_ESTILO_MARCA}"


class EstrategiaVideoVeo(EstrategiaGeracaoVisual):
    # subclasses definem:
    _env_modelo: str = ""
    _modelo_padrao: str = ""
    custo_usd_por_segundo: float = 0.15

    def __init__(self, cliente: genai.Client | None = None):
        self._cliente = cliente

    def _cliente_resolvido(self) -> genai.Client:
        return self._cliente or genai.Client(api_key=_chave_gemini())

    def _modelo(self) -> str:
        modelo = os.environ.get(self._env_modelo) or self._modelo_padrao
        if not modelo:
            raise ErroConfiguracaoAusente(
                f"{self._env_modelo} não configurado no .env e sem default no código."
            )
        return modelo

    def gerar(self, *, roteiro: str, formato: str, nome_base: str | None = None) -> dict[str, Any]:
        cliente = self._cliente_resolvido()
        operacao = cliente.models.generate_videos(
            model=self._modelo(),
            prompt=_prompt_video(roteiro),
            config=types.GenerateVideosConfig(number_of_videos=1),
        )

        while not operacao.done:
            time.sleep(_INTERVALO_POLLING_SEGUNDOS)
            operacao = cliente.operations.get(operacao)

        if operacao.error:
            raise RuntimeError(f"{type(self).__name__}: geração falhou — {operacao.error}")

        videos_gerados = operacao.response.generated_videos
        if not videos_gerados:
            raise RuntimeError(f"{type(self).__name__}: nenhum vídeo retornado pela operação.")

        arquivo_video = videos_gerados[0].video
        dados_binarios = cliente.files.download(file=arquivo_video)
        caminho = salvar_peca_localmente(dados_binarios, "mp4", nome=nome_base)

        return {"peca_url": caminho, "formato": formato}
