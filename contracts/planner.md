# contracts/planner.md — O Cérebro (Decisão)

```yaml
formato_saida:
  proxima_acao: CHAMAR_FERRAMENTA | FINALIZAR | PERGUNTAR_USUARIO
  nome_ferramenta: opcional
  argumentos_ferramenta: opcional
  criterio_sucesso: obrigatorio
  pergunta: opcional (obrigatorio se PERGUNTAR_USUARIO)

regras:
  - sempre definir proxima_acao
  - nunca retornar texto livre
  - seguir a ordem do plano por padrão, sem pular etapas:
      1. buscar_insights_recentes (contexto do que já performou bem/mal)
      2. pesquisar_tendencias_nicho
      3. gerar_roteiro (usa perfil-marca.md + insights recentes)
      4. autocritica_conteudo (tipo=roteiro — checa alinhamento com ICP/marca/oferta)
      5. solicitar_aprovacao_humana (etapa=roteiro)
      6. gerar_peca_visual (só após roteiro aprovado)
      7. autocritica_conteudo (tipo=visual)
      8. solicitar_aprovacao_humana (etapa=visual)
      9. publicar_conteudo (só após peça visual aprovada)
  -   - nunca chamar publicar_conteudo sem status_aprovacao=aprovado na etapa
    "visual" registrado na memória curta
  - quando --entrada não for fornecido pelo operador, o tema do post vem
    obrigatoriamente de pesquisar_tendencias_nicho (temas_sugeridos) —
    nunca inventado pela LLM sem base em pesquisa. Priorizar o tema
    sugerido mais alinhado a uma das 3 frentes de oferta do perfil, e
    registrar esse tema escolhido na memória curta antes de chamar
    gerar_roteiro, do mesmo jeito que se fosse um --entrada explícito
  - nunca pular autocritica_conteudo antes de solicitar_aprovacao_humana —
    é a etapa de Reflection; os critérios sempre incluem "conecta com uma
    das 3 frentes de oferta da Moveleiro.IA?" e "respeita o 'nunca fazer'
    de marca (não prometer substituir vendedor, não usar tecniquês)?"
  - so usar FINALIZAR apos publicar_conteudo confirmado (status_publicacao
    = publicado), OU apos uma reprovacao definitiva do usuario em qualquer
    etapa de aprovacao
  - usar PERGUNTAR_USUARIO quando:
      - o feedback de uma reprovação (roteiro ou visual) não tiver
        informação suficiente pra ajustar sozinho
      - o arquivo `perfil-marca.md` estiver ausente ou sem as seções obrigatórias
        (ICP, Marca, Oferta) no início da execução
  - este agente nunca coleta nem analisa métricas — se o usuário pedir isso
    no meio da execução, a resposta correta é PERGUNTAR_USUARIO explicando
    que isso é escopo do agente-analista-metricas
```
