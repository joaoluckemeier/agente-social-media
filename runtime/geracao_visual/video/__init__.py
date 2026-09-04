"""geracao_visual/video/ — REEL via Veo (Gemini API). Aqui a IA generativa
continua sendo a única opção real: não existe "vídeo de estoque" que sirva
pro roteiro específico de cada post (decisoes-de-engenharia.md, seção 2).

Strategy com tiering por custo:
  - padrão  -> Veo 3.1 Fast   (estrategia_video_padrao.py)   ~$0,15/s
  - premium -> Veo 3.1 completo (estrategia_video_premium.py) ~$0,40/s — só
    reel "carro-chefe". A escolha do tier é lógica interna da Strategy
    (selecionar_video.py), não faz parte do contrato de skill.
"""
