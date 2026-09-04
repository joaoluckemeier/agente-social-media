# contracts/toolbox.md — A Caixa de Ferramentas (Registro)

```yaml
ferramentas:
  - nome: buscar_insights_recentes
    entrada:
      limite: int

  - nome: pesquisar_tendencias_nicho
    entrada:
      nicho: string
      rede: string

  - nome: gerar_roteiro
    entrada:
      tema: string
      perfil: object
      insights_anteriores: list
      formato: string

  - nome: autocritica_conteudo
    entrada:
      conteudo: object
      tipo: string
      criterios: object

  - nome: gerar_peca_visual
    entrada:
      slides: list
      formato: string

  - nome: solicitar_aprovacao_humana
    entrada:
      peca: object
      etapa: string

  - nome: publicar_conteudo
    entrada:
      peca_url: list
      rede: string
      legenda: string
```

Todas as 7 ferramentas acima existem com a mesma assinatura em `skills.md`.
`coletar_metricas` e `gerar_insight_melhoria` foram removidas desta versão
— são responsabilidade do futuro `agente-analista-metricas`.
