"""geracao_visual/ — geração da peça visual final.

Dois caminhos, decididos por formato (decisoes-de-engenharia.md, seção 2):
  - imagem/ (estático, carrossel) -> motor de template HTML/CSS, sem IA
    generativa. Fotos, quando o layout pede, vêm de banco de estoque
    (adapters/fotos_estoque/).
  - video/ (reel) -> Veo (Gemini), Strategy com tier padrão/premium.
"""
