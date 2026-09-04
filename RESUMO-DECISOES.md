# Resumo de decisões — agente-social-media (Moveleiro.IA)

## Rodada 1 — ideação inicial

| Decisão | Escolha | Por quê |
|---|---|---|
| Tipo de agente | `goal_oriented` | Objetivo amplo que se desdobra num plano de fases, não uma tarefa fixa. |
| Arquitetura cognitiva | Plan-Execute + Reflection | Sequência conhecida; autocrítica antes da aprovação evita rascunho fraco. |
| Nº de agentes | 1 (v1) | Fases compartilham o mesmo contexto de negócio. |
| Aprovação | Peça por peça (roteiro → visual) | Decisão explícita do João. |
| Geração visual | Peça final via IA (não só briefing) | Decisão explícita do João. |

## Rodada 2 — ajustes de escopo, identidade e engenharia

| Decisão | Escolha | Por quê |
|---|---|---|
| Métricas | Removidas deste agente | Vira responsabilidade de um `agente-analista-metricas` futuro, evitando complexidade agora. |
| Handoff entre agentes | Banco compartilhado (tabelas `posts`/`insights`), sem chamada direta | Desacopla os dois agentes; cada um só lê/escreve seu repositório. |
| Identidade | Moveleiro.IA (IA para lojas de móveis/marcenaria) | Identidade genérica demais antes — agora tem ICP, marca e oferta reais. |
| Nome do agente | Mantido técnico (`agente-social-media`) | Preferência explícita do João. |
| Contexto de negócio | `perfil-marca.md` (ICP + marca + oferta), via `--perfil` | Preenchido com dor #1 (demora no atendimento) como gancho prioritário. |
| Publicação (rede social) | Adapter → API unificada multi-rede (bundle.social na v1) | Evita acoplamento à Graph API do Instagram; plano gratuito já cobre o volume da v1, plano pago é bem mais barato que a alternativa mais próxima em escala. |
| Geração de imagem | Strategy: modelo baixo custo p/ peça sem texto, modelo especializado em tipografia p/ peça com frase embutida | Eficiência: usa o modelo mais barato que ainda resolve, escala pra um melhor só quando o caso exige (texto na imagem). |
| Geração de vídeo (reel) | Modelo padrão de melhor custo-benefício pra vídeo curto de rede social; modelo premium como fallback com áudio/diálogo | Mesma lógica de eficiência aplicada a vídeo. |
| Banco de dados | SQLite atrás de um Repository (`MemoriaRepository`) | Troca pra Postgres no futuro sem tocar no resto do runtime. |
| Autenticação | Nenhuma de entrada (CLI local, sem API exposta); credenciais de saída em `.env` | Não há chamada externa entrando — JWT não se aplica; API key bastaria se um dia isso virar chamada de rede entre agentes. |

## Rodada 3 — provedor de geração visual

| Decisão | Escolha | Por quê |
|---|---|---|
| Geração de imagem e vídeo | Gemini como único provedor (Nano Banana Pro + Veo) | Decisão explícita do João — prioriza um vendor só (billing/gestão simples) mesmo custando mais por peça que o mix Flux/Ideogram/Kling considerado antes (~5x a 40x mais caro por peça). |
| Acesso à API do Gemini | Precisa de projeto de API com billing próprio | O plano Google AI Pro que o João já assina é uma entitlement do app Gemini, não dá cota de automação — API é cobrada à parte. |

## Rodada 4 — correção de qualidade: template em vez de IA generativa pra imagem

| Decisão | Escolha | Por quê |
|---|---|---|
| Diagnóstico dos testes iniciais | Dois problemas: copy incompleta na peça (só título ia pro carrossel) e identidade visual inconsistente/"cara de IA" | Causa raiz: pedir pra um modelo de imagem desenhar parágrafo inteiro é tecnicamente frágil (texto corrompido), e sem referência visual o modelo cai no estilo genérico padrão dele. |
| Geração de imagem (carrossel/estático) | Sai da IA generativa, vira motor de template por código (HTML/CSS) | Referências reais aprovadas (@brandsdecoded__, Content Machine) mostram que o resultado desejado é 100% tipografia/grid, não foto gerada — template garante texto sempre certo e identidade sempre consistente, com custo quase zero. |
| Fotos (quando o layout pede) | Banco de fotos de estoque real e licenciado (Unsplash), nunca IA | Evita o problema de "gente gerada por IA" que não passa credibilidade. |
| Geração de vídeo (reel) | Continua no Gemini/Veo | Não existe "vídeo de estoque" que sirva pro roteiro específico — aqui IA generativa continua sendo a única opção real. |
| Contrato de `gerar_roteiro` | Saída estruturada em `slides` (com `tipo_layout` por slide), não mais um texto solto | Necessário pro motor de template saber qual template renderizar por slide, e evita a classe de bug de "corpo da copy se perde". |
| Paleta de marca | Tom quente/madeira (bege + terracota) | Escolha explícita do João — remete ao móvel, mantém a linha das referências aprovadas. |

## Rodada 5 — implementação: imagem 100% fora da IA

| Decisão | Escolha | Por quê |
|---|---|---|
| Geração de imagem | Removida toda IA generativa do runtime — inclusive a etapa intermediária com OpenAI Images (gpt-image-1) que uma versão anterior do código usava. Carrossel/estático agora são motor de template (HTML/CSS via Playwright headless). | Fecha a decisão da Rodada 4 no código: template garante texto íntegro e identidade consistente, custo ~zero. Nenhum model id de imagem nem env var de imagem por IA sobra no projeto. |
| `gerar_roteiro` | Saída estruturada: `slides` = lista de `{ordem, tipo_layout, titulo, corpo}` (+ `consulta_foto` só em slides de foto). Nada de `roteiro` de texto solto — o texto é derivado dos slides onde o pipeline precisa (legenda, exibição, comparação de versão). | O motor de template precisa do `tipo_layout` por slide; elimina a classe de bug "corpo da copy se perde". |
| Design tokens | Bloco `yaml` na seção "Identidade Visual" de `perfil-marca.md`, lido por `perfil_loader.py` (merge sobre defaults). | Explícito e testável, sem regex sobre prosa. Tokens continuam vivendo no perfil, não hardcoded. |
| Fotos | `adapters/fotos_estoque/` (Unsplash na v1), acionado só pelos templates `foto_split` / `capa` com `consulta_foto`. | Foto real licenciada, nunca "gente gerada por IA". |
| Vídeo (reel) | Split de tier implementado: `estrategia_video_padrao.py` (Veo 3.1 Fast) + `estrategia_video_premium.py` (Veo 3.1 completo), Strategy escolhe (default padrão). A chamada ao Veo em si não mudou — só foi movida pra uma base compartilhada. | Fidelidade ao `ESTRUTURA-PASTAS.md`; Gemini segue sendo usado só pra vídeo. |

## Entregáveis desta sessão

1. Os 9 contratos em `contracts/` + `agent.md` na raiz (atualizados).
2. `comandos.md` com a extensão `--perfil` apontando pra `perfil-marca.md`.
3. `config-exemplo/perfil-marca.md` — ICP, marca e oferta da Moveleiro.IA.
4. `decisoes-de-engenharia.md` atualizado (Adapter, Strategy, Repository,
   segurança, resiliência, custo).
5. `ESTRUTURA-PASTAS.md` — prévia de módulos Python, incluindo
   `geracao_visual/` (Strategy) e `adapters/redes_sociais/` (Adapter).
6. Este resumo.

## Próximos passos sugeridos

- Revisar `perfil-marca.md` com quem conhece o negócio de perto (Beta ou
  outro sócio) antes de rodar a v1 de verdade.
- Levar a pasta `agente-social-media/` pro Claude Code com o briefing de
  `ESTRUTURA-PASTAS.md`.
- Quando fizer sentido, ideiar o `agente-analista-metricas` como uma nova
  sessão separada neste Project — ele só precisa saber ler a tabela
  `posts` e escrever na tabela `insights`.
