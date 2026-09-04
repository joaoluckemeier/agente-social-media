# memory.md — Memória Curta e Resumo Final

```yaml
memoria_curta:
  guardar:
    - resultado_de_ferramenta
    - decisao_do_planejador
    - insights_recebidos          # vindos de buscar_insights_recentes
    - evidencia_coletada          # tendências e temas sugeridos
    - roteiro_aprovado
    - feedback_de_aprovacao       # motivo de reprovações, se houver
  descartar:
    - prompt_sistema_completo
    - argumentos_mock_internos
    - dados_de_entrada_repetidos
    - versoes_de_roteiro_descartadas_apos_aprovacao
  max_registros: 40

resumo_final:
  max_linhas: 15
  campos:
    - objetivo
    - etapas_executadas
    - ferramentas_chamadas
    - resultado_final
    - proximos_passos
```
