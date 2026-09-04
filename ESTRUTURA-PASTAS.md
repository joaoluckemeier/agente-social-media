# Prévia de estrutura — agente-social-media (Moveleiro.IA)

Isto é um **mapa**, não implementação. É o que o Claude Code vai receber
como briefing pra gerar o código de verdade.

```
agente-social-media/
├── agent.md
├── comandos.md
├── decisoes-de-engenharia.md
├── config-exemplo/
│   └── perfil-marca.md              # ICP + marca + oferta (referenciado via --perfil)
├── contracts/
│   ├── planner.md
│   ├── loop.md
│   ├── toolbox.md
│   ├── rules.md
│   ├── executor.md
│   ├── skills.md
│   ├── hooks.md
│   └── memory.md
│
└── runtime/                         # o que o Claude Code implementa
    ├── cli.py                       # lê comandos.md → "rodar", "validar", "rastreamento"
    ├── perfil_loader.py             # carrega perfil-marca.md e injeta no planejador
    ├── planejador.py                # lê planner.md → decide proxima_acao a cada passo
    ├── ciclo.py                     # lê loop.md → orquestra o ciclo, aplica condicoes_parada
    ├── executor.py                  # lê executor.md → valida entrada, chama ferramenta, retry, avalia resultado
    ├── memoria.py                   # Repository de memória curta + tabela posts (SQLite v1)
    ├── trace.py                     # observabilidade — implementa hooks.md, gera trace.json
    │
    ├── ferramentas/                 # uma implementação por item de skills.md
    │   ├── buscar_insights.py       # lê tabela `insights` (escrita pelo agente-analista-metricas)
    │   ├── pesquisar_tendencias.py
    │   ├── gerar_roteiro.py
    │   ├── autocritica.py
    │   ├── gerar_peca_visual.py     # delega pra geracao_visual/imagem (template) ou /video (Gemini)
    │   ├── aprovacao_humana.py
    │   └── publicar_conteudo.py     # usa adapters/redes_sociais/
    │
    ├── geracao_visual/
    │   ├── imagem/                        # ESTÁTICO/CARROSSEL — 100% template, sem IA generativa
    │   │   ├── motor_template.py          # renderiza HTML/CSS -> imagem (ex: Playwright headless)
    │   │   ├── selecionar_template.py     # Strategy: tipo_layout do slide -> template certo
    │   │   └── templates/                 # um arquivo por tipo_layout (ver skills.md)
    │   │       ├── capa.html
    │   │       ├── texto_grande.html
    │   │       ├── lista_numerada.html
    │   │       ├── diagrama_processo.html
    │   │       ├── comparacao.html
    │   │       ├── foto_split.html
    │   │       └── cta.html
    │   └── video/                         # REEL — só aqui a IA generativa continua fazendo sentido
    │       ├── base_veo.py                   # chamada assíncrona ao Veo (polling/download) — compartilhada
    │       ├── estrategia_video_padrao.py    # Veo 3.1 Fast (veo-3.1-fast-generate-001)
    │       ├── estrategia_video_premium.py   # Veo 3.1 completo (veo-3.1-generate-001) — só reel carro-chefe
    │       └── selecionar_video.py           # Strategy: escolhe o tier (default padrão)
    │
    └── adapters/
        ├── redes_sociais/
        │   ├── base_adapter.py           # interface: publicar()
        │   └── bundle_social_adapter.py  # implementação v1 — API unificada multi-rede
        │       # (futuro: trocar/estender sem tocar no resto do runtime — Adapter + OCP)
        │
        ├── llm/
        │   ├── base_provider.py      # interface: gerar_texto(prompt, ...)
        │   └── openai_provider.py    # implementação v1 — escolhido por custo
        │       # (futuro: trocar por AnthropicProvider/GoogleProvider/etc. sem
        │       #  tocar em planejador.py, executor.py ou nas ferramentas)
        │
        └── fotos_estoque/
            ├── base_adapter.py         # interface: buscar_foto(query) -> url/arquivo
            └── unsplash_adapter.py     # implementação v1 — gratuito, licenciado
```

## Por que cada peça existe

- **`config-exemplo/perfil-marca.md` + `perfil_loader.py`** — é a peça que
  não vem do template padrão do curso: contexto fixo de ICP/marca/oferta
  carregado uma vez por execução, não só a entrada pontual do tema.
- **`geracao_visual/imagem/` (Template Method)** — pivô importante: a
  imagem final **não é gerada por IA**. É um motor de template (código)
  que insere o texto real do slide e, quando o `tipo_layout` pede, compõe
  com uma foto de banco de estoque — nunca desenha texto nem gente via
  modelo de imagem. Resolve os dois problemas identificados nos testes
  iniciais (texto cortado e identidade visual inconsistente) e derruba o
  custo de imagem pra quase zero.
- **`geracao_visual/video/`** — aqui sim a IA generativa (Gemini/Veo)
  continua fazendo sentido, porque não existe "vídeo de estoque" que sirva
  pro roteiro específico de cada post.
- **`adapters/redes_sociais/`** — Adapter + OCP: publica via API unificada
  multi-rede em vez da API nativa do Instagram diretamente, então
  adicionar TikTok/LinkedIn no futuro não toca em `planejador.py`,
  `ciclo.py` nem `executor.py`.
- **`adapters/fotos_estoque/`** — Adapter pro banco de fotos reais
  (Unsplash na v1), usado só pelos templates que pedem foto (`foto_split`,
  `capa` com imagem de fundo).
- **`adapters/llm/`** — mesmo raciocínio pro provedor de LLM: OpenAI foi
  escolhido por custo, mas `gerar_roteiro.py` e `autocritica.py` só
  conhecem `base_provider.py`, nunca o SDK da OpenAI diretamente. Trocar
  de provedor no futuro é implementar um novo Adapter, não reescrever
  ferramenta nenhuma.
- **`memoria.py`** — Repository: troca de SQLite pra Postgres é isolada
  aqui, e é o ponto de encontro (tabelas `posts`/`insights`) com o futuro
  `agente-analista-metricas`, sem chamada direta entre os dois agentes.
