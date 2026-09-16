# skills.md — A Ficha Técnica das Ferramentas

```yaml
habilidades:
  - nome: buscar_insights_recentes
    descricao: >
      Lê a tabela de insights gerada pelo agente-analista-metricas (banco
      compartilhado) e retorna as recomendações mais recentes, pra
      alimentar o próximo roteiro. Não é chamada de API externa — é
      leitura de repositório.
    entrada:
      limite: int
    saida:
      insights: list

  - nome: pesquisar_tendencias_nicho
    descricao: >
      Busca temas e formatos em alta dentro do nicho (IA para lojas de
      móveis/marcenaria), na rede indicada, pra alimentar a geração de
      roteiro.
    entrada:
      nicho: string
      rede: string
    saida:
      tendencias: list
      temas_sugeridos: list

  - nome: gerar_roteiro
    descricao: >
      Gera o roteiro de um conteúdo a partir de um tema, do perfil-marca.md
      (ICP, marca, oferta) e dos insights recentes, garantindo conexão com
      uma das 3 frentes de oferta. A saída é estruturada por slide, não um
      texto solto — cada slide já indica que tipo de layout de template usar
      (ver decisoes-de-engenharia.md, seção 2), pra garantir que o texto
      completo sempre chegue certo na peça visual. Também gera a legenda e
      as hashtags do post (separadas dos slides — a legenda complementa o
      carrossel no feed, não repete o texto dele).
    entrada:
      tema: string
      perfil: object
      insights_anteriores: list
      formato: string   # reel | carrossel | estatico
    saida:
      slides: list      # cada item: {ordem, tipo_layout, titulo, corpo}
      legenda: string   # texto autônomo pro feed — gancho + contexto + CTA
      hashtags: list    # 3 a 5, do catálogo de perfil-marca.md (seção Hashtags)
      formato: string

  - nome: autocritica_conteudo
    descricao: >
      Etapa de Reflection: avalia os slides de um roteiro ou uma peça
      visual contra critérios de qualidade E de aderência ao
      perfil-marca.md (conecta com a oferta? respeita o "nunca fazer" de
      marca? tom está certo? o tipo_layout escolhido por slide faz sentido
      pro conteúdo daquele slide?) antes de submeter à aprovação humana.
    entrada:
      conteudo: object    # slides (tipo=roteiro) ou peca_url (tipo=visual)
      tipo: string        # roteiro | visual
      criterios: object
    saida:
      aprovado_internamente: bool
      ajustes_sugeridos: list

  - nome: gerar_peca_visual
    descricao: >
      Gera a peça visual final a partir dos slides do roteiro já aprovado.
      Para estático/carrossel: renderiza cada slide por um motor de
      template (código, não IA generativa) escolhido pelo `tipo_layout` do
      slide, usando os design tokens de `perfil-marca.md` e, quando o
      layout pedir foto, uma foto real de um banco de fotos de estoque.
      Para reel: gera vídeo via API do Gemini (Veo). Qual mecanismo é
      usado por tipo de peça é interno à implementação — não faz parte
      deste contrato. Ver decisoes-de-engenharia.md, seção 2.
    entrada:
      slides: list
      formato: string
    saida:
      peca_url: list
      formato: string

  - nome: solicitar_aprovacao_humana
    descricao: >
      Apresenta uma peça (roteiro ou visual) para aprovação do usuário e
      aguarda decisão. Peça por peça — nunca em lote.
    entrada:
      peca: object
      etapa: string        # roteiro | visual
    saida:
      aprovado: bool
      feedback: string

  - nome: publicar_conteudo
    descricao: >
      Publica a peça aprovada na rede social, via adapter que fala com uma
      API unificada de publicação multi-rede (ver decisoes-de-engenharia.md,
      seção 2 — Adapter). Ação sensível.
    entrada:
      peca_url: list
      rede: string
      legenda: string
    saida:
      post_id: string
      status: string
      publicado_em: string
```

Nota: `coletar_metricas` e `gerar_insight_melhoria` existiam numa versão
anterior deste contrato e foram removidas — passam a ser responsabilidade
do `agente-analista-metricas`, um agente separado.

Nota: valores válidos de `tipo_layout` (usado em `gerar_roteiro` e
`gerar_peca_visual`): `capa`, `texto_grande`, `lista_numerada`,
`diagrama_processo`, `comparacao`, `foto_split`, `cta`. Cada um corresponde
a um template concreto — ver `ESTRUTURA-PASTAS.md` e a Identidade Visual
em `perfil-marca.md`.
