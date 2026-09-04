# comandos.md — A CLI (o Agente como Produto)

```yaml
comandos:
  - nome: rodar
    descricao: executa o agente com uma entrada
    argumentos:
      - nome: --agente
        obrigatorio: true
        descricao: caminho para a pasta do agente (agente-social-media/)
      -       - nome: --entrada
        obrigatorio: false
        descricao: >
          tema ou objetivo inicial (ex: "post sobre demora no atendimento
          do WhatsApp"). Opcional — se omitido, o agente escolhe o tema
          sozinho a partir de pesquisar_tendencias_nicho e
          buscar_insights_recentes (comportamento goal_oriented: o
          objetivo amplo já basta, o agente decide o próximo conteúdo).
      - nome: --perfil
        obrigatorio: true
        descricao: >
          caminho para perfil-marca.md — documento com ICP, marca, oferta e
          diretrizes de conteúdo (ver config-exemplo/perfil-marca.md).
          Carregado uma vez no início da execução e injetado no planner.
          [EXTENSÃO desta ideação — não existe no template genérico do
          curso, adicionado porque este agente precisa de contexto
          persistente de nicho/marca/oferta entre execuções.]

  - nome: validar
    descricao: valida se os 9 contratos estao completos e consistentes entre si
    argumentos:
      - nome: --agente
        obrigatorio: true
        descricao: caminho para a pasta do agente

  - nome: rastreamento
    descricao: exibe o trace da ultima execucao (observabilidade)
    argumentos: []
```

O exemplo completo de `perfil-marca.md` (ICP, marca e oferta da
Moveleiro.IA) está em `config-exemplo/perfil-marca.md`.
