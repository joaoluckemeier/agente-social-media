# API.md — casca HTTP interna do agente-social-media

Interface **estável e interna** que o componente `front-end`
(`~/agents/front-end/`) consome como cliente externo. Não substitui o CLI —
`python -m runtime.cli rodar ...` continua igual, para uso manual.

## Princípios (arquitetura.md — "Segurança dessa interface interna")

- **Bind só em `127.0.0.1`.** Nunca `0.0.0.0`. O Caddy não deve ter rota
  apontando para esta porta. Só processos na mesma VPS a alcançam.
- **Chave compartilhada** (`AGENTE_API_KEY`, header `X-API-Key`) verificada em
  todo request. Não é JWT — é conexão máquina-a-máquina com um único chamador.
- **Sem caminho paralelo mais permissivo.** Toda ação reusa a lógica de
  `runtime/` que o CLI já usa (ex: validação de perfil = a mesma
  `PerfilMarca.secoes_faltando()` do `planejador.py` / comando `validar`).
- **Observabilidade.** Toda chamada vai para `dados/trace-api.jsonl`
  (append-only, mesmo formato de evento do `runtime/trace.py`), com
  `origem="api"`, `chamador`, rota, método e resultado. O header opcional
  `X-Chamador` é só rótulo (ex: `front-end:tenant-1`), nunca autorização.

## Rodar

```bash
cd ~/agents/agente-social-media
source venv/bin/activate
pip install -r requirements-api.txt
python -m api.app            # respeita AGENTE_API_HOST/PORT do .env
# ou: uvicorn api.app:app --host 127.0.0.1 --port 8790
```

`.env` (ver `.env.example`): `AGENTE_API_KEY` (obrigatória), `AGENTE_API_HOST`,
`AGENTE_API_PORT`, `PERFIL_PATH`, `DATABASE_PATH`, `EXEC_MAX_POR_HORA/DIA`.

## Endpoints (v0.1 — Etapa 1)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/saude` | não | Liveness. |
| GET | `/versao` | sim | Versão do componente. |
| GET | `/posts?limite=&offset=` | sim | Histórico de posts (tabela `posts`). Mais recentes primeiro. |
| GET | `/posts/{post_id}` | sim | Um post. 404 se não existe. |
| GET | `/perfil` | sim | Perfil de marca atual, **estruturado** (nunca YAML cru): `nicho/rede/tom/icp/marca/oferta/identidade_visual/secoes_extras/secoes_faltando`. |
| PUT | `/perfil` | sim | Reescreve o `perfil-marca.md` real a partir da forma estruturada. `422` com `secoes_faltando` se o resultado seria inválido — o arquivo real fica intacto. Escrita atômica. |

### Fila de aprovação (Etapa 2)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/aprovacoes/pendentes` | sim | Pendências aguardando decisão: `{pendentes: [{id, execucao_id, etapa, peca, criado_em}]}`. `etapa` ∈ `roteiro`\|`visual`\|`publicacao`. |
| POST | `/aprovacoes/{id}/decidir` | sim | Body `{aprovado: bool, feedback?: str}`. Grava a decisão e **retoma o ciclo** em background. `409` se a pendência já foi decidida. A lógica de aprovação (ordem roteiro→visual→publicação, gate de ação sensível) continua no `planejador.py`/`executor.py` — aqui só se registra a linha. |
| POST | `/execucoes` | sim | Body `{entrada?: str, formato?: reel\|carrossel\|estatico}`. Dispara um `rodar` em background (`202`). **`409`** se já há execução ativa/suspensa (trava de concorrência). **`429`** `{janela, limite}` se o rate limit local (`EXEC_MAX_POR_HORA`/`DIA`) estourou — 2ª camada, a 1ª é no backend do front-end. |
| GET | `/execucoes/{id}` | sim | Estado: `{execucao_id, estado, entrada, formato, segundos_ativos, motivo_parada, pergunta_aberta, atualizado_em}`. `estado` ∈ `rodando`\|`suspensa`\|`aguardando_intervencao`\|`finalizada`\|`erro`\|`descartada`. |

**Suspende/retoma:** ao chegar numa aprovação sem decisão, o ciclo levanta
`RunSuspensa` e o worker marca `execucao_ativa.estado = suspensa`. O
`limite_tempo_segundos` (`loop.md`) conta só processamento ativo —
`segundos_ativos` acumulado exclui o tempo parado esperando o humano (`loop.md`
tem uma nota sobre `max_etapas` também não ser cumulativo entre retomadas — o
backstop real é `chamadas_ferramenta.total`, que É cumulativo). Reprovar com
feedback gera uma nova pendência (o planejador regenera e a peça muda de hash).

O CLI (`python -m runtime.cli retomar --agente . --perfil <arq> --execucao-id <id>`)
retoma manualmente uma execução suspensa, se precisar.

### Mídia (Etapa 3)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/pecas/{arquivo}` | sim | Serve o PNG real de `dados/pecas/`. `peca.pecas_urls` (fila) e `posts.peca_url` (histórico) já vêm reescritos como `/pecas/<arquivo>` em vez do path absoluto de disco (`api/media.py`) — fecha a lacuna documentada em `geracao_visual/base_estrategia.py` (skills.md pedia uma URL de verdade). |

4 camadas de validação antes de tocar disco (`{arquivo}` vem de fora):
1. regex fechado (`api/rotas/pecas.py`): `^post_[a-z0-9_]+_slide\d+\.png$` —
   já bloqueia `/` e `..` por construção, não é a única barreira;
2. o caminho é resolvido e precisa continuar dentro de `dados/pecas/`
   depois de resolvido (`Path.is_relative_to`) — defesa em profundidade,
   mesmo que o regex acima algum dia mude;
3. só `.png` é servido, nunca outra extensão (reel/vídeo fica de fora —
   sem rota pra servir ainda);
4. o nome precisa corresponder a uma peça **registrada** (em `posts`,
   `aprovações` etapa visual/publicação, ou `resultado_de_ferramenta` de
   `gerar_peca_visual` de alguma execução) — nunca só "existe um arquivo
   com esse nome na pasta" (`memoria.peca_registrada`).

### Perguntas abertas e descartar (Etapa 3)

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/execucoes/aguardando` | sim | Execuções paradas em `PERGUNTAR_USUARIO` (perfil incompleto, feedback vazio, pedido de métricas...): `{execucoes: [ExecucaoOut]}`. |
| GET | `/execucoes/{id}/trace` | sim | Trace bruto e completo (`{execucao_id, eventos}}`) — o agente não filtra por papel, quem faz isso é o backend do front-end (ver `decisoes.md` dele). `404` se não é a execução mais recente (`dados/trace.json` guarda só uma por vez). |
| POST | `/execucoes/{id}/descartar` | sim | Move a execução pra `estado=descartada` e cancela qualquer aprovação `pendente` órfã. **`404`** se não existe. **`409`** se está `rodando` ou já `descartada` — nunca `200` sem ter descartado de verdade. |

Um `PERGUNTAR_USUARIO` no modo fila encerra a execução em
`estado=aguardando_intervencao` (não `finalizada`) com `motivo_parada =
aguardando_intervencao_operador` e `pergunta_aberta` preenchido. Esse estado
**também segura a trava** de `POST /execucoes` (mesmo filtro de
`execucao_em_andamento`) — o agente não tem re-injeção de resposta livre (nem
o CLI tem), então o modelo é "corrige a causa (ex: completa o
`perfil-marca.md`) e descarta essa execução antes de disparar outra", não
"responde e continua".

## O que esta casca NÃO faz

- Não expõe nada à internet.
- Não edita a tabela `posts` nem o banco por fora do runtime.
- Não reimplementa validação de regra de negócio — delega a `runtime/`.
- Não recebe segredo de negócio (isso é `perfil-marca.md`, versionado à parte).
