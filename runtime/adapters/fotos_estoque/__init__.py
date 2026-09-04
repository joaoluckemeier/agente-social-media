"""adapters/fotos_estoque/ — Adapter pro banco de fotos de estoque real e
licenciado (decisoes-de-engenharia.md, seção 2).

Quando um `tipo_layout` pede foto (`foto_split`, ou `capa` com imagem de
fundo), a foto vem daqui — nunca de um modelo de geração de imagem. v1:
Unsplash. Trocar por Pexels/outro é implementar `FotoEstoqueAdapter` de
novo, sem tocar no motor de template.
"""
