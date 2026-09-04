# agente-social-media (Moveleiro.IA)

Agente `goal_oriented` que pesquisa temas ligados às dores de donos de loja
de móveis/marcenaria, roteiriza um conteúdo conectado a uma das 3 frentes de
oferta da Moveleiro.IA, gera a peça visual, busca aprovação humana peça por
peça e publica no Instagram.

O comportamento completo está especificado nos contratos (`agent.md`,
`comandos.md`, `contracts/*.md`, `decisoes-de-engenharia.md`) — este README
cobre só como configurar e rodar o `runtime/`.

> **Estado atual:** motor (`cli.py`, `planejador.py`, `ciclo.py`,
> `executor.py`, `memoria.py`, `trace.py`, `perfil_loader.py`) e as 7
> ferramentas (`ferramentas/`, `geracao_visual/`, `adapters/`) estão
> implementados.
>
> **Arquitetura de imagem (decisão revista — `decisoes-de-engenharia.md`,
> seção 2):** carrossel/estático **não usam IA generativa**. `gerar_roteiro`
> devolve `slides` estruturados (`{ordem, tipo_layout, titulo, corpo}`) e um
> **motor de template** renderiza cada slide em HTML/CSS -> PNG com Chromium
> headless (Playwright), usando os design tokens de `perfil-marca.md`. Onde o
> layout pede foto (`foto_split`, `capa` com imagem), a foto vem do
> **Unsplash** (`adapters/fotos_estoque/`) — nunca gerada por IA. Texto
> sempre íntegro, identidade consistente, custo de imagem ~zero.
>
> **Vídeo (reel):** continua no **Veo (Gemini)**, agora com Strategy de tier
> padrão/premium (`geracao_visual/video/`). **Duas partes ainda têm
> incerteza real e precisam ser validadas contra API/documentação oficial
> antes do primeiro uso em produção** (ver seção 5): a superfície exata do
> SDK `google-genai` pra Veo, e o endpoint/payload da API da bundle.social.

## 1. Setup

```bash
cd agente-social-media
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # navegador headless p/ o motor de template

cp .env.example .env
# edite .env e preencha:
#   OPENAI_API_KEY, OPENAI_MODEL_ROTEIRO, OPENAI_MODEL_AUTOCRITICA
#   UNSPLASH_ACCESS_KEY          (só se algum slide usar foto — foto_split / capa)
#   GEMINI_API_KEY, GEMINI_MODEL_VIDEO_PADRAO / _PREMIUM  (só p/ reel — projeto
#                                 de API com billing próprio, a assinatura do
#                                 app Gemini NÃO conta)
#   BUNDLE_SOCIAL_API_KEY, BUNDLE_SOCIAL_ACCOUNT_ID_INSTAGRAM
#   DATABASE_PATH               (opcional; default: dados/agente.db)
```

O `.env` nunca é commitado (ver `.gitignore`). Nenhuma credencial fica
hardcoded em nenhum contrato ou módulo — tudo vem de variável de ambiente.
Não há chave de API de geração de imagem: carrossel/estático são 100%
template.

## 2. Rodar

Todos os comandos são executados como módulo Python, de dentro da pasta
`agente-social-media/`:

```bash
python -m runtime.cli validar --agente .
```
Confere se os 9 contratos existem e são consistentes entre si. **Aviso
conhecido (pré-existente, não relacionado à arquitetura de imagem):**
`validar` acusa `contracts/rules.md` com um bloco YAML tecnicamente inválido
(pontuação de texto corrido dentro de itens de lista) — revisar a pontuação
lá se quiserem o `validar` 100% limpo.

```bash
python -m runtime.cli rodar \
  --agente . \
  --entrada "post sobre demora no atendimento do WhatsApp" \
  --perfil config-exemplo/perfil-marca.md \
  --formato carrossel
```
Executa o ciclo completo: `buscar_insights_recentes` →
`pesquisar_tendencias_nicho` → `gerar_roteiro` (slides estruturados) →
`autocritica_conteudo` → `solicitar_aprovacao_humana` (roteiro) →
`gerar_peca_visual` → `autocritica_conteudo` → `solicitar_aprovacao_humana`
(visual) → `publicar_conteudo`. Aceita `--formato reel|carrossel|estatico`
(default `reel`).

**Carrossel gera 1 imagem por slide** (`pecas_visuais_urls` é uma lista;
arquivos nomeados `{post_id}_slide{ordem}.png`) — o
número de slides vem do próprio roteiro (normalmente 5–9). Cada peça é uma
renderização de template (sem custo de API); só slides `foto_split`/`capa`
com `consulta_foto` fazem 1 chamada ao Unsplash. `reel` gera 1 vídeo via Veo.

`publicar_conteudo` é uma **ação sensível** (`contracts/rules.md`): antes de
executá-la o CLI pede confirmação explícita (`s/N`). `solicitar_aprovacao_humana`
(roteiro e peça visual) também é sempre um prompt síncrono, peça por peça.

```bash
python -m runtime.cli rastreamento
```
Mostra o `dados/trace.json` da última execução.

## 3. Persistência

SQLite em `dados/agente.db` (não versionado), sempre acessado através de
`MemoriaRepository` (`runtime/memoria.py`). Tabelas: `memoria_curta`,
`posts`, `insights` (escrita pelo futuro `agente-analista-metricas`, só lida
aqui via `buscar_insights_recentes`), `cache` (só `pesquisar_tendencias_nicho`,
TTL 6h), `resumos_finais`.

Peças visuais (`gerar_peca_visual`) são salvas localmente em `dados/pecas/`
(`runtime/geracao_visual/base_estrategia.salvar_peca_localmente`);
`publicar_conteudo` faz upload direto desses arquivos pra bundle.social.

## 4. Custo

`gerar_roteiro` e `autocritica_conteudo` gravam tokens reais de uso da
OpenAI. **Imagem não tem custo de IA** — é template + foto de estoque
grátis. Reel (Veo) usa uma estimativa fixa em USD por tier (~$0,15/s padrão,
~$0,40/s premium — `geracao_visual/video/`). Tudo agregado em
`resumo_final.custo_estimado` (visível também em `rastreamento`).

## 5. Antes do primeiro uso em produção

- **Playwright:** confirme que `playwright install chromium` rodou sem erro
  no ambiente (o motor de template levanta `ErroConfiguracaoAusente` com
  instrução clara se o Chromium não estiver instalado).
- **Veo (`geracao_visual/video/base_veo.py`, só p/ reel):** a chamada ao SDK
  `google-genai` (`generate_videos` assíncrono) segue o padrão documentado
  no momento desta implementação — não foi testada contra a API real. Rodar
  um teste manual com a `GEMINI_API_KEY` real antes de confiar em produção.
- **bundle.social (`adapters/redes_sociais/bundle_social_adapter.py`):**
  endpoint e payload (`_endpoint_criar_post`/`_montar_payload`) foram
  implementados sem acesso confirmado à documentação oficial mais recente.
- Revisar `config-exemplo/perfil-marca.md` (inclusive o bloco de design
  tokens da seção "Identidade Visual") com quem conhece o negócio.
- Primeiras execuções: recusar a confirmação final de `publicar_conteudo`
  (responder `n`) pra validar roteiro/peça/custo sem publicar nada.

## 6. Estrutura

Ver `ESTRUTURA-PASTAS.md` para o mapa completo: Template Method em
`geracao_visual/imagem/`, Strategy em `geracao_visual/video/`, Adapter em
`adapters/redes_sociais/` e `adapters/fotos_estoque/`, Repository em
`memoria.py`.
