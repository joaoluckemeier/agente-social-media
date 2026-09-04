# rules.md — O Livro de Regras (Limites)

```yaml
ferramentas_obrigatorias:
  - solicitar_aprovacao_humana   # obrigatória nas etapas "roteiro" e "visual" antes de avançar

limites:
  max_etapas: 12
  sem_progresso: 3
  limite_tempo_segundos: 1800
  chamadas_ferramenta:
    buscar_insights_recentes: 1
    pesquisar_tendencias_nicho: 2
    gerar_roteiro: 3
    gerar_peca_visual: 3
    publicar_conteudo: 1
    total: 16

acoes_sensiveis:
  - publicar_conteudo

politicas:
  - publicar_conteudo só pode ocorrer depois de status_aprovacao=aprovado
    registrado explicitamente pelo usuário na etapa "visual" — nunca por
    inferência do agente.
  - aprovação é peça por peça - roteiro precisa ser aprovado antes de gerar
    a peça visual; peça visual precisa ser aprovada antes de publicar.
  - toda rede social é acessada por trás de um adapter dedicado
    (`rede_social_adapter`), que na v1 fala com uma API unificada de
    publicação multi-rede (não a API nativa de cada rede diretamente).
    Isso permite adicionar TikTok/LinkedIn no futuro trocando só a
    configuração da conta conectada, sem alterar `planner`, `loop` ou
    `executor` (ver decisoes-de-engenharia.md, seção 2 — Adapter).
  - v1 publica apenas no Instagram (`rede "instagram"` no perfil).
    - todo o contexto de negócio (ICP, marca, oferta, tom, "nunca fazer")
    vive em `perfil-marca.md`, carregado uma única vez no início da
    execução via `--perfil` (ver `comandos.md`) — nunca hardcoded em
    nenhum contrato ou ferramenta.
  - `--entrada` é opcional. Quando omitido, o tema do post é escolhido
    pelo próprio agente a partir de `pesquisar_tendencias_nicho`, nunca
    inventado sem base de pesquisa — essa é a diferença entre um agente
    `goal_oriented` de verdade e um `task_based` disfarçado.
  - `autocritica_conteudo` é obrigatória em roteiro e em visual, e seus
    critérios sempre incluem checar conexão com a oferta e aderência ao
    "nunca fazer" de marca — não é só qualidade estética/textual.
  - coleta e análise de métricas estão fora de escopo deste agente; a
    ponte com o `agente-analista-metricas` é via banco compartilhado
    (tabelas `posts` e `insights`), nunca chamada direta entre agentes.
  - hoje `publicar_conteudo` sempre passa por confirmação humana (v1 - você
    publica manualmente com a peça aprovada, ou aprova a publicação
    automática dentro do próprio fluxo). O contrato já está pronto para o
    dia em que a política mudar, sem reescrever o restante dos contratos.
```
