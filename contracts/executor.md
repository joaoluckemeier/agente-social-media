# contracts/executor.md — O Braço (Execução)

```yaml
execucao:
  validar_entrada: true
  tentar_novamente_em_falha: true
pos_execucao:
  avaliar_resultado: true
```

Nota de extensão (documentada aqui, decisão desta ideação): as ferramentas
`gerar_peca_visual` e `publicar_conteudo` chamam serviços externos (API de
geração de imagem/vídeo e API do Instagram) que falham por instabilidade de
rede — mais que o padrão. Retry com backoff exponencial pra essas duas
específicas está detalhado em `decisoes-de-engenharia.md`, seção 6, e cabe
ao Claude Code implementar; o contrato aqui permanece no padrão do runtime.
