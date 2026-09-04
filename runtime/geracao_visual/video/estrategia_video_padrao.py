"""geracao_visual/video/estrategia_video_padrao.py — tier padrão de reel.

Veo 3.1 Fast (`GEMINI_MODEL_VIDEO_PADRAO`, default `veo-3.1-fast-generate-001`),
~$0,15/s — qualidade quase idêntica ao tier completo, ~2x mais rápido; é o
que a documentação do Google recomenda como padrão de produção
(decisoes-de-engenharia.md, seção 2).
"""

from __future__ import annotations

from .base_veo import EstrategiaVideoVeo


class EstrategiaVideoPadrao(EstrategiaVideoVeo):
    _env_modelo = "GEMINI_MODEL_VIDEO_PADRAO"
    _modelo_padrao = "veo-3.1-fast-generate-001"
    custo_usd_por_segundo = 0.15
