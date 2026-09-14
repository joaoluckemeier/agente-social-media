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

Nota (extensão — componente `front-end`, fila de aprovação): a etapa de
aprovação humana pode ser servida por um `GatewayAprovacao` assíncrono
(`runtime/aprovacao/`) em vez do prompt síncrono do CLI. Nesse modo o ciclo
**suspende** ao chegar numa aprovação sem decisão registrada e é **retomado**
depois — o planejador reconstrói todo o estado de `memoria_curta`, então não
há caminho de validação paralelo. Isso não é uma `condicao_parada` (a
execução continua depois), e `limite_tempo_segundos` conta só o tempo de
processamento ativo: o intervalo suspenso, aguardando o humano, fica de fora.
No modo assíncrono, um `PERGUNTAR_USUARIO` (sem stdin no servidor) encerra a
execução com o motivo `aguardando_intervencao_operador` — o operador corrige
(ex: completa o `perfil-marca.md`) e dispara de novo.

Nota (extensão — `max_etapas` vs. suspende/retoma): `max_etapas` é contado
**por invocação de `executar_ciclo()`** e reinicia a cada `retomar_ciclo()`.
Ele NÃO é o backstop contra loop infinito ao longo de múltiplas suspensões da
mesma execução — cada retomada ganha um orçamento novo de 12 iterações (na
prática, um segmento de retomada só executa 2‑3 passos novos, porque o
planejador devolve a próxima ação e não re‑itera as já feitas). O backstop
cumulativo real é `limites.chamadas_ferramenta.total` de `rules.md` (16):
`executor._verificar_limites` conta as linhas `resultado_de_ferramenta` de
`memoria_curta` por `execucao_id`, que persistem entre suspensões — então o
teto de chamadas vale para a execução inteira, não por segmento.
