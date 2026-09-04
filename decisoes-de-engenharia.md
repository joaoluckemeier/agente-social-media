# decisoes-de-engenharia.md — agente-social-media (Moveleiro.IA)

## 1. Princípios SOLID aplicados ao runtime

**Decisão deste agente:** o ponto de atenção específico é o **OCP na
camada de redes sociais e na camada de geração visual**: adicionar uma
rede nova (TikTok, LinkedIn) ou um provedor novo de imagem/vídeo não pode
exigir alterar `planejador.py` nem `executor.py` — só um adapter/estratégia
novo e uma entrada em `toolbox.md`/`skills.md`. Ver seção 2.

## 2. Design Patterns

**Decisão deste agente:**

- **Adapter — publicação em rede social.** `publicar_conteudo` nunca fala
  com a API nativa de uma rede diretamente. Fala com uma interface
  `RedeSocialAdapter` (`publicar()`), implementada na v1 por
  `BundleSocialAdapter`, que usa uma API unificada de publicação
  multi-rede (bundle.social) em vez da Graph API do Meta diretamente.
  Motivo: a Graph API do Instagram exige app review, só funciona com
  conta Business/Creator e tem fluxo específico por tipo de mídia (reel,
  carrossel, story), o que criaria acoplamento forte a uma única rede.
  Uma API unificada resolve reel/carrossel/estático/story pela mesma
  chamada e já nasce pronta pra outras redes. Custo do plano gratuito da
  bundle.social (3 contas, 20 posts/mês) já cobre o volume da v1; se subir
  de volume, o plano Pro ($100/mês, contas ilimitadas) é bem mais barato
  que o piso da Ayrshare (~$149–299/mês) no mesmo cenário.

- **Adapter — provedor de LLM.** `gerar_roteiro` e `autocritica_conteudo`
  nunca chamam o SDK de um provedor de LLM diretamente. Falam com uma
  interface `LLMProvider` (`gerar_texto(prompt, ...)`), implementada na
  v1 por `OpenAIProvider` — decisão por custo (ver seção 12). Trocar pra
  Anthropic, Google ou outro provedor no futuro é só implementar
  `AnthropicProvider`/etc. e apontar a config pra ela, sem tocar em
  `planejador.py`, `ciclo.py`, `executor.py` nem nas ferramentas que usam
  LLM. É o mesmo raciocínio de OCP já aplicado às redes sociais (Adapter)
  e à geração visual (Strategy).

- **Template Method — renderização de imagem (estático/carrossel), sem
  IA generativa.** Decisão revista após avaliar qualidade real: gerar
  imagem inteira via IA (mesmo Gemini) produzia texto cortado/corrompido e
  identidade visual inconsistente entre peças. A solução correta aqui não
  é IA — é um **motor de template** (HTML/CSS renderizado via navegador
  headless, ex: Playwright) com um template por `tipo_layout` de slide:
  `capa`, `texto_grande`, `lista_numerada`, `diagrama_processo`,
  `comparacao`, `foto_split`, `cta`. O texto (título + corpo inteiro do
  roteiro) é sempre inserido como texto real no template — nunca desenhado
  por um modelo de imagem — então nunca sai cortado ou corrompido. As
  cores, tipografia e estrutura de cabeçalho/rodapé vêm dos design tokens
  em `perfil-marca.md`, garantindo que toda peça saia com a mesma
  identidade visual (é isso que resolve o "parece cara de IA").

- **Adapter — banco de fotos de estoque.** Quando um `tipo_layout` pede
  foto (`foto_split`, ou uma `capa` com imagem de fundo), a foto vem de um
  banco de fotos de estoque real e licenciado (Unsplash/Pexels, grátis),
  nunca de um modelo de geração de imagem — evita o problema de "gente
  gerada por IA" que não passa credibilidade. Acessado via
  `FotoEstoqueAdapter`, trocável entre Unsplash/Pexels/outro sem tocar no
  motor de template.

- **Strategy — geração de vídeo (reel), Gemini único provedor, com
  tiering por custo.** Aqui a IA generativa continua sendo a única opção
  (não existe "banco de vídeo de estoque" que sirva pro roteiro
  específico), então mantém o Gemini/Veo:
    - Padrão → **Veo 3.1 Fast** (`veo-3.1-fast-generate-001`, estável/GA),
      ~$0,15/segundo — qualidade quase idêntica ao tier completo, ~2x mais
      rápido, e é o que a própria documentação do Google recomenda como
      padrão de produção.
    - Escalar pra **Veo 3.1 padrão** (`veo-3.1-generate-001`), ~$0,40/segundo,
      só pra reel "carro-chefe" que precisa da qualidade máxima.
    - **Veo 3.1 Lite** (`veo-3.1-lite-generate-preview`, ~$0,05–0,08/s)
      existe e é ainda mais barato, mas fica de fora da v1 por ainda estar
      em status *preview* — não é adequado pra peça final que vai pro ar.
  - A decisão de qual tier de vídeo usar (reel carro-chefe?) é lógica
    interna da Strategy, não faz parte do contrato de skill.
  - **Nomes de modelo mudam com frequência** — confirmar o ID atual na
    documentação do Gemini antes de codar, o mesmo cuidado já registrado
    pro LLM (seção 12).

- **Repository — persistência.** `memoria.py` isola a persistência da
  memória curta (`memory.md`) e da tabela `posts` por trás de uma
  interface (`MemoriaRepository`), independente do banco escolhido. Ver
  seção 3.

- **Facade** — o ciclo completo é exposto ao operador via um único
  comando `rodar` (`comandos.md`).

## 3. Modelagem de Banco de Dados / Persistência

**Decisão deste agente:** **SQLite** na v1, sempre por trás da interface
`MemoriaRepository` — nunca acessado diretamente pelo resto do runtime.
Isso resolve duas coisas ao mesmo tempo:
- **Migração pra Postgres:** se o volume crescer, troca-se
  `SQLiteMemoriaRepository` por `PostgresMemoriaRepository` sem tocar em
  `planejador.py`, `ciclo.py` ou `executor.py`.
- **Compartilhamento com o `agente-analista-metricas`:** as tabelas
  `posts` (escrita por este agente) e `insights` (escrita pelo agente de
  métricas, lida por este agente via `buscar_insights_recentes`) vivem no
  mesmo banco. Os dois agentes nunca se chamam diretamente — só leem/
  escrevem no repositório compartilhado.

Tabelas mínimas: `posts` (post_id, tema, roteiro, peca_url, rede,
status_aprovacao, status_publicacao, publicado_em), `insights` (post_id,
insight, recomendacao, gerado_por, gerado_em).

## 4. Estratégia de Cache

**Decisão deste agente:** cache exato e curto (ex: 6h) só em
`pesquisar_tendencias_nicho` — tendências de nicho não mudam de hora em
hora. As demais ferramentas não se beneficiam de cache.

## 5. Autenticação e Segurança de APIs

**Decisão deste agente:** o agente **não expõe nenhuma API própria** na
v1 — roda só via CLI local (`rodar`). Não há chamada de fora entrando, então
não há necessidade de JWT ou qualquer mecanismo de autenticação de entrada.

O que existe são credenciais de saída, todas em `.env` (nunca versionado):
- chave da API unificada de publicação (bundle.social) + tokens OAuth2 das
  contas conectadas;
- chave da API do Gemini (só vídeo/Veo agora, seção 2) — **atenção:** essa
  chave vem de um projeto de API/Google AI Studio com billing próprio,
  separado da assinatura Google AI Pro do app Gemini que o João já paga.
  A assinatura do app não libera cota de automação — é preciso criar (ou
  já ter) um projeto de desenvolvedor com billing ativado antes do Claude
  Code integrar isso;
- chave da API de fotos de estoque (Unsplash/Pexels) — gratuita, mas ainda
  assim uma credencial, vai no `.env` como as demais;
- `OPENAI_API_KEY` — GPT (modelo intermediário para `gerar_roteiro`,
  modelo mini/menor para `autocritica_conteudo`), ver seção 12. Acessado
  sempre via `LLMProvider` (Adapter, seção 2) — trocar de provedor no
  futuro é uma config, não uma reescrita.

Confiável porque a superfície de ataque é pequena: um único operador
confiável, sem endpoint exposto à internet, entrada validada antes de virar
argumento de ferramenta. Quando o `agente-analista-metricas` existir, a
comunicação é via banco compartilhado (seção 3) — não uma chamada de rede
entre os dois agentes, então também não exige autenticação ali. Se um dia
esse handoff precisar virar uma chamada de rede (ex: agentes em máquinas
diferentes), uma API key estática já resolve — JWT só passaria a valer a
pena se isso virar um produto com múltiplos usuários/clientes externos
autenticando na API do agente, o que não é o caso hoje.

## 6. Tratamento de Erros e Resiliência

**Decisão deste agente:** retry com **backoff exponencial** em
`gerar_peca_visual` e `publicar_conteudo` (serviços externos sujeitos a
instabilidade), com timeout explícito de 60s por chamada de imagem e 120s
por chamada de vídeo (geração de vídeo demora mais). `gerar_peca_visual`
tem no máximo 2 retries por ser a chamada mais cara (custo real por
tentativa, ver seção 2) — falhar rápido e escalar pra aprovação humana é
mais barato que insistir sozinho. As demais ferramentas usam retry simples
(1 nova tentativa). O circuit breaker geral já vem do `loop.md`
(`max_etapas`, `sem_progresso`, `limite_tempo_segundos`).

## 7. Gestão de Configuração e Segredos

**Decisão deste agente:** `.env` para credenciais (bundle.social, provedor
de imagem, provedor de vídeo, LLM). `perfil-marca.md` fica versionado
separadamente por não ser segredo — é o produto/contexto de negócio,
referenciado via `--perfil`.

## 8. Observabilidade

**Decisão deste agente:** logging estruturado em JSON. Rastrear por
execução: custo estimado de tokens (LLM) e de geração de imagem/vídeo
(por provedor, já que os preços variam bastante entre eles — seção 2), e
taxa de reprovação por etapa (roteiro vs visual), que indica se
`perfil-marca.md` está calibrado ou se o problema é recorrente numa etapa
específica.

## 9. Orquestração Multiagente (se aplicável)

**Decisão deste agente:** dois agentes na arquitetura completa —
`agente-social-media` (este) e o futuro `agente-analista-metricas` — mas
**sem orquestrador central na v1**. Eles se comunicam de forma assíncrona
via banco compartilhado (tabelas `posts` e `insights`, seção 3), não por
chamada direta agente-a-agente. Se um dia precisar de coordenação mais
ativa (ex: disparar o agente de conteúdo automaticamente quando um insight
novo chega), reavaliar com um `goal_oriented` coordenador — decisão
adiada, não tomada agora.

## 10. Testes e Evals

**Decisão deste agente:** a métrica de qualidade que mais importa aqui não
é "rodou sem erro" — é **taxa de aprovação na primeira tentativa** (roteiro
e visual aprovados sem pedir ajuste) e, depois que o agente de métricas
existir, **correlação entre insight recebido e melhora de aprovação no
ciclo seguinte**.

## 11. Deploy e Infraestrutura

**Decisão deste agente:** execução local via CLI na v1. Migrar para
agendamento (cron/APScheduler) só faz sentido quando/se `publicar_conteudo`
deixar de exigir aprovação síncrona.

## 12. Gestão de Custo

**Decisão deste agente:** contagem real de tokens por execução (LLM) e
custo real por chamada de imagem/vídeo — nunca estimativa. Provedor de LLM
definido: **OpenAI**, via `OPENAI_API_KEY` — escolhido por custo. Acesso
sempre via `LLMProvider` (Adapter, seção 2) — o provedor fica
deliberadamente aberto pra troca; se o custo ou a qualidade do OpenAI
deixarem de compensar, é questão de implementar um novo Adapter, não de
reescrever o agente.

**Critério de escolha de tier (não um nome de modelo travado — a OpenAI
muda nome/preço com frequência; confirmar o modelo atual na documentação
da OpenAI no momento da implementação):**
- `autocritica_conteudo` → **`gpt-4o-mini`** (escolha concreta desta
  implementação — geração anterior, mas ainda mais barata que o tier
  "Nano" atual, e suficiente pra uma tarefa de julgamento, não de criação).
  Sinal de alerta pra trocar: se a autocrítica aprovar internamente
  roteiros que a aprovação humana reprova com frequência por não captar
  nuance de tom/marca, subir pra um tier "nano" da geração atual — troca
  de config no `OpenAIProvider`, não reescrita.
- `gerar_roteiro` → o tier intermediário (linha "Mini" ou equivalente), não
  o flagship. Qualidade suficiente pra copy curta de rede social por uma
  fração do custo do modelo topo de linha; se a qualidade não for
  suficiente na prática, subir de tier é só uma mudança de config no
  `OpenAIProvider`, não uma reescrita.

Com a imagem saindo do fluxo de IA generativa (template renderizado por
código + fotos de estoque grátis, seção 2), o custo por peça de imagem
caiu pra praticamente zero — sobrou só o custo de vídeo (Veo) como
variável real de orçamento por execução. `chamadas_ferramenta` em
`rules.md` limitando `gerar_peca_visual` a 3 tentativas continua valendo,
mas agora o impacto financeiro de um retry é desprezível pra imagem e
relevante só pra reel — vale considerar um orçamento máximo por execução
com alerta focado especificamente no gasto de vídeo.
