# contracts/loop.md — O Motor (Ciclo)

```yaml
objetivo: gerar_conteudo_engajante_conectado_a_oferta
ciclo:
  max_etapas: 12   # 9 etapas do plano feliz + margem para 1 rodada de ajuste em roteiro e 1 em visual

condicoes_parada:
  - objetivo_alcancado          # publicar_conteudo confirmado (status_publicacao = publicado)
  - max_etapas_excedido
  - sem_progresso               # ex: 3 tentativas de ajuste de roteiro sem aprovação
  - limite_tempo_excedido
  - confirmacao_humana_negada   # reprovação definitiva
```

Nota: `max_etapas` caiu de 14 para 12 depois de remover as 2 etapas de
métricas/insight do fluxo (decisão desta sessão — ver `agent.md`, seção
"Fronteira com outros agentes").
