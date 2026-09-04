"""ferramentas/autocritica.py — skills.md: autocritica_conteudo.

Etapa de Reflection: avalia roteiro ou peça visual contra critérios de
qualidade E de aderência ao perfil-marca.md, antes da aprovação humana.
Provedor: OpenAI, modelo mais barato/rápido (OPENAI_MODEL_AUTOCRITICA —
decisoes-de-engenharia.md, seção 12: "tarefa de julgamento").

planner.md exige que os critérios sempre incluam conexão com a oferta e
aderência ao "nunca fazer" de marca — isso já vem em `criterios`, montado
por planejador.py (`_criterios_autocritica`) com o texto real da seção
Oferta/Marca do perfil, não só a pergunta — então o prompt aqui só formaliza
o julgamento, não redecide o que checar.

Extensão de engenharia (achada rodando de verdade, não estava nos
contratos): quando `tipo == "visual"` e `conteudo` aponta pra um arquivo de
imagem local existente (caso de gerar_peca_visual salvando em
dados/pecas/), anexamos a imagem de verdade na chamada — OPENAI_MODEL_AUTOCRITICA
precisa ser um modelo com visão (gpt-4o-mini e a maioria dos modelos atuais
da OpenAI são). Sem isso, o modelo só via o caminho do arquivo como texto e
não tinha como julgar nada de verdade — ficava hedgeando e reprovando por
rotina até estourar o limite de chamadas de gerar_peca_visual (rules.md).
Vídeo (reel) continua sem anexo (chat multimodal de imagem não serve pra
vídeo) — cai no fallback textual, mais permissivo por não conseguir checar.

Extensão de engenharia (pedido explícito, custo real): quando várias peças
são anexadas (carrossel), o modelo também aponta QUAIS índices têm problema
concreto (`pecas_com_problema`) — `planejador.py`/`gerar_peca_visual.py`
usam isso pra regenerar só as peças com defeito, não o carrossel inteiro.
Sem índice apontado com citação concreta, nenhuma peça é considerada com
problema (mesma régua anti-hedge do resto do prompt).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from .. import ErroConfiguracaoAusente

_EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_SYSTEM_PROMPT = """\
Você é um revisor crítico de conteúdo para redes sociais da Moveleiro.IA. \
Avalie o CONTEÚDO fornecido contra a lista de CRITÉRIOS fornecida — cada \
critério já vem com o trecho real do perfil de marca (oferta, tom, "nunca \
fazer") que você precisa usar como referência; não é uma pergunta abstrata.

Seja rigoroso, não complacente — o objetivo é pegar problema real antes da \
aprovação humana. Mas rigoroso não é o mesmo que evasivo: pra cada \
critério, dê um veredito DECISIVO (passou ou não passou), nunca uma \
ressalva do tipo "verificar se..." ou "confirmar se...". Se o critério \
passa, diga que passa e siga em frente — não invente incerteza sobre algo \
que o próprio conteúdo (texto ou imagem) já responde.

Quando `tipo` for "roteiro": `conteudo` é a lista de SLIDES estruturados \
do roteiro — cada slide tem `ordem`, `tipo_layout`, `titulo` e `corpo`. \
Você tem o roteiro inteiro na sua frente; julgue-o diretamente, com uma \
citação ou paráfrase do trecho (titulo/corpo de um slide) que sustenta seu \
veredito em cada critério. Não hedge alegando que "não dá pra saber" algo \
que está escrito nos próprios slides. Se `criterios` incluir uma chave \
sobre `tipo_layout`, avalie se o `tipo_layout` escolhido em cada slide faz \
sentido pro conteúdo daquele slide (ex: `lista_numerada` só quando o corpo \
é de fato uma lista; `capa` no slide 1; `cta` no fechamento; `foto_split` \
só quando uma foto real agrega) — cite o(s) slide(s) por `ordem` quando \
reprovar.

Quando `tipo` for "visual" E uma ou mais imagens estiverem anexadas a esta \
mensagem (um carrossel manda várias — `numero_de_pecas` no contexto diz \
quantas, e cada imagem vem logo depois de um texto "Peça N:" indicando seu \
índice, 1 a numero_de_pecas): você PODE VER cada imagem de verdade — julgue \
TODAS elas, com a mesma régua decisiva do roteiro. As peças são renderizadas \
por um motor de template (o texto é sempre texto real, nunca desenhado por \
IA) — então NÃO reprove por "texto cortado/ilegível/corrompido"; concentre \
o julgamento em identidade visual, escolha de layout, e a foto real quando \
houver. Um critério só passa pro \
conjunto se passar em CADA peça anexada. IMPORTANTE: quando uma peça \
específica tiver problema, você DEVE listar o índice dela em \
`pecas_com_problema` (ver formato de resposta abaixo) — isso é o que \
permite regenerar só aquela peça em vez do carrossel inteiro, então nunca \
deixe de apontar o índice quando reprovar algo. Os critérios de texto (Oferta/Marca) \
se aplicam de um jeito DIFERENTE numa imagem: cada peça é só uma capa/cena \
de um slide, sem o roteiro inteiro escrito nela — a legenda com o texto \
completo (oferta, CTA, disclaimer sobre o vendedor) vai separada, no post. \
Então:
- "Conecta com a oferta" numa imagem = a CENA é relevante ao tema (loja de \
móveis/marcenaria, atendimento, WhatsApp, orçamento, ambiente de loja) — \
NÃO exige texto escrito na imagem confirmando isso.
- "Respeita o nunca fazer" numa imagem = a cena não RETRATA a IA \
substituindo o vendedor (ex: um robô/tela sozinha no lugar de uma pessoa \
atendendo, loja vazia de gente) e não é clipart genérico de robô/IA. Se a \
imagem só mostra um ambiente de loja, celular, atendimento ou pessoas — \
sem sugerir substituição — isso PASSA, mesmo sem nenhum texto sobre o \
tema escrito nela.
Só reprove um critério visual se a CENA em si contradiz a regra (ex: mostra \
literalmente um robô no balcão sem vendedor), não pela ausência de texto \
que nunca deveria estar na imagem.

Quando `tipo` for "visual" e NENHUMA imagem estiver anexada (ex: reel em \
vídeo, ou arquivo indisponível): `conteudo` é só a URL/caminho do arquivo, \
você não pode julgar o conteúdo visual de fato. Nesse caso, e só nesse \
caso, avalie só o que dá pra inferir por texto (ex: se foi gerado a partir \
de um roteiro já aprovado, formato correto) e liste em ajustes_sugeridos \
só o que precisaria de checagem visual humana — sem reprovar por rotina.

Atenção específica pro critério de "nunca fazer" (não prometer substituir \
vendedor) — vale tanto pra texto quanto pra imagem: a peça PRECISA falar/\
mostrar IA perto de "vendedor"/"atendimento" — é o tema do post. A regra \
proíbe dizer/sugerir que a IA SUBSTITUI/FAZ O PAPEL DO vendedor. Uma peça \
que diz o contrário — "a IA não substitui o vendedor", "o vendedor \
continua no centro", "ela complementa/apoia o vendedor" — CUMPRE a regra, \
não viola. Só reprove esse critério se a peça afirmar ou sugerir de \
verdade que a IA substitui, dispensa ou faz o trabalho do vendedor — nunca \
só por mostrar/citar as duas coisas juntas.

Exemplos (mesmo critério "não promete substituir vendedor", em texto):
- "a IA ajuda a dar a primeira resposta e complementa o trabalho do \
vendedor no atendimento" → PASSA. É um complemento, o vendedor segue no \
centro; a frase até reforça isso explicitamente.
- "a IA responde, organiza e cuida do atendimento pra você" (sem nunca \
mencionar ou implicar um vendedor humano em nenhuma parte do conteúdo) → \
PASSA. Ausência de menção ao vendedor não é o mesmo que prometer substituí-lo.
- "com a IA, você não precisa mais de vendedor pra fechar venda" → NÃO \
PASSA. Aqui sim a IA está sendo apresentada como substituta.
Use esses três como calibração de onde fica a linha — a maioria das peças \
vai cair no primeiro ou segundo caso, e ambos passam.

Pra cada chave de `criterios`, você DEVE citar o trecho exato (palavra por \
palavra) do conteúdo — ou, pra imagem, descrever o elemento visual exato — \
que sustenta seu veredito, ANTES de decidir passou/não passou. Se você não \
consegue apontar um trecho/elemento concreto que viole a regra, o \
critério passou — não existe reprovação sem uma citação/descrição \
específica apontando o problema.

Responda SOMENTE em JSON, no formato exato:
{
  "avaliacoes": {
    "<chave do critério, uma entrada por chave de CRITÉRIOS>": {
      "citacao": "<trecho exato ou descrição do elemento visual que embasa o veredito; null se não há nada a apontar>",
      "passou": <bool>
    }
  },
  "pecas_com_problema": [
    {"indice": <int, 1-based, só quando houver imagens anexadas>, "citacao": "<elemento visual exato dessa peça>", "ajuste": "<o que mudar nessa peça específica>"}
  ],
  "ajustes_sugeridos": ["<ajuste 1>", ...]
}
Um critério só pode ter `passou: false` se `citacao` apontar concretamente \
o problema (não pode ser null nem um resumo vago tipo "pode sugerir..."). \
`pecas_com_problema` fica vazio quando não há imagens anexadas ou quando \
todas as peças passam — mesma regra de citação obrigatória. \
`ajustes_sugeridos` fica vazio quando tudo passa.\
"""


def _chave_openai() -> str:
    chave = os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise ErroConfiguracaoAusente(
            "OPENAI_API_KEY não configurado no .env (ver .env.example) — "
            "necessário para chamadas à OpenAI."
        )
    return chave


def _modelo() -> str:
    modelo = os.environ.get("OPENAI_MODEL_AUTOCRITICA")
    if not modelo:
        raise ErroConfiguracaoAusente(
            "OPENAI_MODEL_AUTOCRITICA não configurado no .env — defina o "
            "modelo OpenAI a usar em autocritica_conteudo (ver .env.example) "
            "— precisa suportar visão pra avaliar peça visual de verdade "
            "(gpt-4o-mini e a maioria dos modelos atuais da OpenAI suportam)."
        )
    return modelo


def _imagens_anexaveis(conteudo: str, tipo: str) -> list[Path]:
    """Carrossel manda várias peças em `conteudo` (uma por linha — ver
    planejador.py). Retorna todos os caminhos que são imagens locais de
    verdade, na ordem — pode ser 1 (estático) ou várias (carrossel)."""
    if tipo != "visual":
        return []
    caminhos = []
    for linha in conteudo.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        caminho = Path(linha)
        if caminho.suffix.lower() in _EXTENSOES_IMAGEM and caminho.is_file():
            caminhos.append(caminho)
    return caminhos


def _montar_mensagem_usuario(
    conteudo: str, tipo: str, criterios: dict[str, Any]
) -> str | list[dict[str, Any]]:
    imagens = _imagens_anexaveis(conteudo, tipo)
    contexto = {"tipo": tipo, "criterios": criterios}

    if not imagens:
        corpo_conteudo: Any = conteudo
        if tipo == "roteiro":
            # planejador.py passa os slides estruturados como JSON — embute
            # já parseado pra o modelo enxergar ordem/tipo_layout/titulo/corpo.
            try:
                corpo_conteudo = json.loads(conteudo)
            except (json.JSONDecodeError, TypeError):
                corpo_conteudo = conteudo
        return json.dumps({**contexto, "conteudo": corpo_conteudo}, ensure_ascii=False)

    contexto["numero_de_pecas"] = len(imagens)
    partes: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(contexto, ensure_ascii=False)}]
    for indice, caminho_imagem in enumerate(imagens, start=1):
        mime = mimetypes.guess_type(caminho_imagem.name)[0] or "image/png"
        b64 = base64.b64encode(caminho_imagem.read_bytes()).decode("ascii")
        partes.append({"type": "text", "text": f"Peça {indice}:"})
        partes.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return partes


def autocritica_conteudo(
    *, conteudo: str, tipo: str, criterios: dict[str, Any], **_: Any
) -> dict[str, Any]:
    """entrada: {conteudo, tipo, criterios} · saida: {aprovado_internamente: bool, ajustes_sugeridos: list}"""
    cliente = OpenAI(api_key=_chave_openai())

    resposta = cliente.chat.completions.create(
        model=_modelo(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _montar_mensagem_usuario(conteudo, tipo, criterios)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    dados = json.loads(resposta.choices[0].message.content)
    avaliacoes = dados.get("avaliacoes")
    if isinstance(avaliacoes, dict) and avaliacoes:
        # formato novo (com citação obrigatória) — só reprova se houver
        # citação concreta apontando o problema, mesma regra do prompt.
        criterios_passaram = all(
            bool(v.get("passou")) or not v.get("citacao")
            for v in avaliacoes.values()
            if isinstance(v, dict)
        )
    else:
        # fallback: modelo não seguiu o formato novo — usa o veredito
        # direto, se veio.
        criterios_passaram = bool(dados.get("aprovado_internamente", False))

    # só reprova por peça se houver citação concreta (mesma regra anti-hedge)
    pecas_com_problema = [
        p for p in (dados.get("pecas_com_problema") or [])
        if isinstance(p, dict) and p.get("indice") and p.get("citacao")
    ]
    indices_com_problema = sorted({int(p["indice"]) for p in pecas_com_problema})

    aprovado_internamente = criterios_passaram and not indices_com_problema

    saida: dict[str, Any] = {
        "aprovado_internamente": aprovado_internamente,
        "ajustes_sugeridos": dados.get("ajustes_sugeridos", []) if not aprovado_internamente else [],
    }
    if indices_com_problema:
        # extensão — não é do contrato de skills.md, mas é o que permite
        # regenerar só a(s) peça(s) com defeito (planejador.py/gerar_peca_visual.py).
        saida["indices_com_problema"] = indices_com_problema

    if resposta.usage is not None:
        saida["_custo"] = {
            "provedor": "openai",
            "modelo": _modelo(),
            "tokens_entrada": resposta.usage.prompt_tokens,
            "tokens_saida": resposta.usage.completion_tokens,
        }
    return saida
