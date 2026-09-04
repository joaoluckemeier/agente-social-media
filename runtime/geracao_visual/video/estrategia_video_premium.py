"""geracao_visual/video/estrategia_video_premium.py — tier premium de reel.

Veo 3.1 completo (`GEMINI_MODEL_VIDEO_PREMIUM`, default `veo-3.1-generate-001`),
~$0,40/s — só para o reel "carro-chefe" que precisa da qualidade máxima
(decisoes-de-engenharia.md, seção 2). A decisão de usar este tier é interna
à Strategy (`selecionar_video.py`), não faz parte do contrato de skill.
"""

from __future__ import annotations

from .base_veo import EstrategiaVideoVeo


class EstrategiaVideoPremium(EstrategiaVideoVeo):
    _env_modelo = "GEMINI_MODEL_VIDEO_PREMIUM"
    _modelo_padrao = "veo-3.1-generate-001"
    custo_usd_por_segundo = 0.40
