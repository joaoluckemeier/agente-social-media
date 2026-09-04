"""geracao_visual/video/selecionar_video.py — Strategy: escolhe o tier de
vídeo.

Default: **padrão** (Veo 3.1 Fast). Premium (Veo 3.1 completo) só quando
`carro_chefe=True` chega em `gerar_peca_visual` — extensão opcional, fora do
contrato de skill (decisoes-de-engenharia.md, seção 2: "a decisão de qual
tier de vídeo usar é lógica interna da Strategy"). Nada seta `carro_chefe`
hoje ⇒ na prática é sempre padrão, com o premium disponível sem reescrita.
"""

from __future__ import annotations

from .base_veo import EstrategiaVideoVeo
from .estrategia_video_padrao import EstrategiaVideoPadrao
from .estrategia_video_premium import EstrategiaVideoPremium


def selecionar_estrategia_video(*, carro_chefe: bool = False) -> EstrategiaVideoVeo:
    return EstrategiaVideoPremium() if carro_chefe else EstrategiaVideoPadrao()
