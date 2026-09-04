# hooks.md — Observação e Intervenção

```yaml
ganchos:
  antes_da_etapa: log
  apos_etapa: log
  antes_da_acao: log
  apos_acao: log
  em_erro: alerta
```

Nota de extensão (decisão desta ideação): além do padrão acima, toda
execução de uma `acao_sensivel` (hoje: `publicar_conteudo`, ver `rules.md`)
dispara `alerta` em vez de `log` no gancho `antes_da_acao` — é o ponto onde
a confirmação humana é exigida. Isso é um refinamento sobre o valor único
do template padrão, documentado aqui explicitamente.
