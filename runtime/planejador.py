"""planejador.py — o cérebro (implementa contracts/planner.md).

Decide, a cada passo, a `proxima_acao` (CHAMAR_FERRAMENTA | FINALIZAR |
PERGUNTAR_USUARIO) olhando pro histórico de resultados de ferramenta já
gravados na memória curta (via MemoriaRepository) — nunca em variável solta,
pra a decisão ser sempre reconstruível a partir do estado persistido.

A ordem das 9 etapas e as regras de quando pular pra PERGUNTAR_USUARIO/
FINALIZAR são as de planner.md, literalmente. Onde o contrato não define um
detalhe (ex: como formato/legenda são escolhidos, como o feedback de uma
reprovação vira novo argumento pra gerar_roteiro/gerar_peca_visual), a
adaptação está comentada inline.

Sem `--entrada` (comandos.md/planner.md), o tema do post é escolhido a
partir de `pesquisar_tendencias_nicho` (`temas_sugeridos`), priorizando o
mais alinhado a uma das 3 frentes de oferta do perfil, e gravado uma vez na
memória curta (`tema_escolhido`) — daí pra frente é tratado igual a um
`--entrada` explícito (`_tema_efetivo` / `_escolher_tema_sugerido`).

Roteiro estruturado por slide (skills.md / agent.md — decisão revista, ver
decisoes-de-engenharia.md, seção 2): `gerar_roteiro` devolve `slides`
(lista de `{ordem, tipo_layout, titulo, corpo}`). Onde o pipeline precisa
do roteiro como texto (legenda de publicação, exibição, chave de comparação
"esta autocrítica/aprovação é da versão atual?"), ele é derivado dos slides
por `roteiro_como_texto`. `gerar_peca_visual` recebe os `slides` + os design
tokens (`identidade_visual`) e devolve `pecas_urls` (1 peça por slide).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from .memoria import MemoriaRepository
from .perfil_loader import PerfilMarca

ProximaAcao = Literal["CHAMAR_FERRAMENTA", "FINALIZAR", "PERGUNTAR_USUARIO"]


# planner.md: critérios que a autocrítica sempre precisa checar, além de
# qualidade estética/textual. `criterios` é `object` em skills.md — nenhum
# contrato exige que seja só a pergunta; embutir o conteúdo real da seção
# Oferta/Marca do perfil aqui (em vez de só a pergunta genérica) é o que dá
# pra autocritica_conteudo julgar de verdade, já que ela não recebe `perfil`
# como argumento separado (entrada fixa de skills.md: conteudo/tipo/criterios).
def _criterios_autocritica(perfil: PerfilMarca) -> dict[str, str]:
    oferta = perfil.secoes.get("Oferta", "(seção Oferta não encontrada no perfil)")
    marca = perfil.secoes.get("Marca", "(seção Marca não encontrada no perfil)")
    return {
        "conecta_com_oferta": (
            "Conecta com uma das 3 frentes de oferta da Moveleiro.IA, descritas "
            f"abaixo (mesmo que sutilmente)?\n\n{oferta}"
        ),
        "respeita_nunca_fazer": (
            "Respeita o tom de voz e o 'nunca fazer' de marca descritos abaixo?"
            f"\n\n{marca}"
        ),
        # decisão revista (skills.md: autocritica_conteudo) — o tipo_layout de
        # cada slide precisa fazer sentido pro conteúdo daquele slide.
        "tipo_layout_adequado": (
            "Para tipo=roteiro: o `tipo_layout` escolhido em cada slide faz "
            "sentido pro conteúdo do slide (capa no slide 1; lista_numerada só "
            "quando o corpo é uma lista; diagrama_processo só quando são passos; "
            "cta no fechamento; foto_split só quando uma foto real agrega)? "
            "Para tipo=visual: o layout renderizado corresponde ao conteúdo."
        ),
    }


# Não especificado nos contratos (skills.md/comandos.md não têm um argumento
# de formato de peça) — default explícito, documentado como suposição.
FORMATO_PADRAO = "reel"

# Palavras comuns de pt-BR que não ajudam a medir alinhamento entre um tema
# sugerido e uma frente de oferta.
_STOPWORDS_PT = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos",
    "nas", "um", "uma", "uns", "umas", "para", "pra", "por", "com", "sem",
    "que", "se", "ao", "aos", "como", "mais", "menos", "ou", "the", "of",
    "and", "seu", "sua", "seus", "suas",
}


def _tokens_significativos(texto: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[0-9a-zà-ú]+", (texto or "").lower())
        if len(t) > 2 and t not in _STOPWORDS_PT
    }


def _frentes_de_oferta(perfil: PerfilMarca) -> list[str]:
    """As linhas numeradas da seção Oferta do perfil — as "3 frentes de
    oferta" citadas em planner.md/rules.md."""
    oferta = perfil.secoes.get("Oferta", "")
    return [
        linha.strip()
        for linha in re.findall(r"^\s*\d+[.)]\s*(.+)$", oferta, re.MULTILINE)
        if linha.strip()
    ]


def _escolher_tema_sugerido(temas: list[str], perfil: PerfilMarca) -> str | None:
    """planner.md/rules.md: sem --entrada, o tema do post vem de
    pesquisar_tendencias_nicho (temas_sugeridos), priorizando o mais alinhado
    a uma das 3 frentes de oferta do perfil.

    Alinhamento = nº de tokens significativos que o tema divide com a frente
    de oferta mais próxima. Em empate (inclusive todos com score 0), vence o
    primeiro da lista — `temas_sugeridos` já vem ordenada por relevância pela
    fonte de tendências. Retorna None só se não houver tema sugerido nenhum."""
    temas = [t.strip() for t in (temas or []) if isinstance(t, str) and t.strip()]
    if not temas:
        return None
    frentes = [_tokens_significativos(f) for f in _frentes_de_oferta(perfil)]
    if not any(frentes):
        return temas[0]

    def alinhamento(tema: str) -> int:
        toks = _tokens_significativos(tema)
        return max((len(toks & frente) for frente in frentes), default=0)

    # max() devolve o primeiro elemento de score máximo — mantém a ordem da
    # pesquisa como desempate.
    return max(temas, key=alinhamento)


def _tema_efetivo(
    memoria: MemoriaRepository,
    execucao_id: str,
    perfil: PerfilMarca,
    entrada: str | None,
    resultado_tendencias: dict[str, Any],
) -> str | None:
    """O tema do post. Com --entrada explícito, é ele. Sem --entrada
    (planner.md/rules.md), é escolhido uma única vez a partir de
    temas_sugeridos e gravado na memória curta como `tema_escolhido`; daí pra
    frente o pipeline (gerar_roteiro, aprovação, trace, tabela posts) trata os
    dois casos igual. Retorna None se rodou sem --entrada e a pesquisa não
    trouxe tema sugerido nenhum."""
    if entrada and entrada.strip():
        return entrada.strip()

    registros = memoria.listar_memoria(execucao_id, tipo="tema_escolhido")
    if registros:
        return registros[-1].conteudo.get("tema")

    temas = (resultado_tendencias.get("saida") or {}).get("temas_sugeridos", [])
    escolhido = _escolher_tema_sugerido(temas, perfil)
    if escolhido is None:
        return None
    memoria.guardar_memoria(
        execucao_id,
        "tema_escolhido",
        {"tema": escolhido, "origem": "temas_sugeridos", "candidatos": temas},
    )
    return escolhido

_PALAVRAS_METRICAS = (
    "métrica",
    "metrica",
    "analytics",
    "engajamento numérico",
    "taxa de conversão",
    "taxa de conversao",
    "desempenho dos posts",
    "roi",
)


def _pede_metricas(texto: str | None) -> bool:
    if not texto:
        return False
    baixo = texto.lower()
    return any(p in baixo for p in _PALAVRAS_METRICAS)


def roteiro_como_texto(slides: list[dict[str, Any]]) -> str:
    """Serialização determinística dos slides pra texto — usada como legenda
    de publicação, exibição na aprovação e chave de comparação de versão.
    Mesmo conjunto de slides -> mesma string, sempre."""
    partes: list[str] = []
    for s in slides or []:
        titulo = str(s.get("titulo") or "").strip()
        corpo = str(s.get("corpo") or "").strip()
        bloco = "\n".join(x for x in (titulo, corpo) if x)
        if bloco:
            partes.append(bloco)
    return "\n\n".join(partes)


def _slides_json(slides: list[dict[str, Any]]) -> str:
    """Chave estável dos slides (pra autocritica.conteudo e comparação)."""
    return json.dumps(slides or [], ensure_ascii=False, sort_keys=True)


@dataclass
class Decisao:
    proxima_acao: ProximaAcao
    criterio_sucesso: str
    nome_ferramenta: str | None = None
    argumentos_ferramenta: dict[str, Any] | None = None
    pergunta: str | None = None


def _historico(memoria: MemoriaRepository, execucao_id: str) -> list[dict[str, Any]]:
    """Registros de tipo resultado_de_ferramenta, em ordem cronológica."""
    return [r.conteudo for r in memoria.listar_memoria(execucao_id, tipo="resultado_de_ferramenta")]


def _ultimo(historico: list[dict[str, Any]], ferramenta: str, **filtro_args: Any) -> dict[str, Any] | None:
    for registro in reversed(historico):
        if registro.get("ferramenta") != ferramenta:
            continue
        argumentos = registro.get("argumentos") or {}
        if all(argumentos.get(k) == v for k, v in filtro_args.items()):
            return registro
    return None


def decidir_proxima_acao(
    *,
    memoria: MemoriaRepository,
    execucao_id: str,
    perfil: PerfilMarca,
    entrada: str | None = None,
    formato: str = FORMATO_PADRAO,
) -> Decisao:
    # 1) perfil-marca.md ausente ou incompleto -> PERGUNTAR_USUARIO (regra
    #    explícita de planner.md).
    if not perfil.valido():
        faltando = ", ".join(perfil.secoes_faltando()) or "arquivo inteiro"
        return Decisao(
            proxima_acao="PERGUNTAR_USUARIO",
            criterio_sucesso="usuário indica como completar/corrigir o perfil-marca.md",
            pergunta=(
                f"O perfil-marca.md ({perfil.caminho}) está incompleto — faltam as "
                f"seções obrigatórias: {faltando}. Como devo prosseguir?"
            ),
        )

    # 2) fora de escopo: pedido de métricas no meio da execução -> planner.md
    if _pede_metricas(entrada):
        return Decisao(
            proxima_acao="PERGUNTAR_USUARIO",
            criterio_sucesso="usuário confirma entendimento do limite de escopo",
            pergunta=(
                "Coleta e análise de métricas estão fora do escopo deste agente "
                "(ver agent.md, 'Fronteira com outros agentes') — isso é "
                "responsabilidade do agente-analista-metricas. Quer que eu "
                "prossiga só com a parte de geração/publicação de conteúdo?"
            ),
        )

    hist = _historico(memoria, execucao_id)

    # 1. buscar_insights_recentes ------------------------------------
    resultado_insights = _ultimo(hist, "buscar_insights_recentes")
    if resultado_insights is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="buscar_insights_recentes",
            argumentos_ferramenta={"limite": 5},
            criterio_sucesso="lista de insights retornada (pode ser vazia)",
        )
    insights_recentes = resultado_insights["saida"].get("insights", [])

    # 2. pesquisar_tendencias_nicho -----------------------------------
    resultado_tendencias = _ultimo(hist, "pesquisar_tendencias_nicho")
    if resultado_tendencias is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="pesquisar_tendencias_nicho",
            argumentos_ferramenta={"nicho": perfil.nicho, "rede": perfil.rede},
            criterio_sucesso="tendências e temas sugeridos retornados",
        )

    # tema do post: --entrada explícito, ou escolhido agora a partir de
    # temas_sugeridos e gravado na memória curta (planner.md/rules.md). Daqui
    # pra frente todo uso é `tema`, nunca `entrada` cru.
    tema = _tema_efetivo(memoria, execucao_id, perfil, entrada, resultado_tendencias)
    if tema is None:
        return Decisao(
            proxima_acao="PERGUNTAR_USUARIO",
            criterio_sucesso="usuário fornece um tema pro post",
            pergunta=(
                "Rodei sem --entrada e pesquisar_tendencias_nicho não devolveu "
                "nenhum tema sugerido pra eu escolher. Qual tema você quer pro post?"
            ),
        )

    # -- estado do roteiro: última geração, autocrítica e aprovação ----
    tentativas_roteiro = [r for r in hist if r.get("ferramenta") == "gerar_roteiro"]
    ultimo_roteiro = tentativas_roteiro[-1] if tentativas_roteiro else None

    if ultimo_roteiro is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_roteiro",
            argumentos_ferramenta={
                "tema": tema,
                "perfil": perfil.as_dict(),
                "insights_anteriores": insights_recentes,
                "formato": formato,
                "temas_recentes": memoria.temas_recentes(limite=10),
            },
            criterio_sucesso="roteiro estruturado em slides gerado",
        )

    slides_atual: list[dict[str, Any]] = ultimo_roteiro["saida"].get("slides") or []
    roteiro_texto = roteiro_como_texto(slides_atual)
    conteudo_roteiro = _slides_json(slides_atual)

    # 4. autocritica_conteudo(tipo=roteiro) -- só sobre a versão mais nova
    autocriticas_roteiro = [
        r for r in hist if r.get("ferramenta") == "autocritica_conteudo"
        and (r.get("argumentos") or {}).get("tipo") == "roteiro"
    ]
    autocritica_roteiro_atual = None
    if autocriticas_roteiro and autocriticas_roteiro[-1]["argumentos"].get("conteudo") == conteudo_roteiro:
        autocritica_roteiro_atual = autocriticas_roteiro[-1]

    if autocritica_roteiro_atual is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="autocritica_conteudo",
            argumentos_ferramenta={
                "conteudo": conteudo_roteiro,
                "tipo": "roteiro",
                "criterios": _criterios_autocritica(perfil),
            },
            criterio_sucesso="reflection concluída: aprovado_internamente definido",
        )

    if not autocritica_roteiro_atual["saida"].get("aprovado_internamente"):
        ajustes = autocritica_roteiro_atual["saida"].get("ajustes_sugeridos", [])

        # blindagem estrutural: regenerar de novo aqui estouraria
        # chamadas_ferramenta.gerar_roteiro (rules.md: 3) — a execução caía
        # em sem_progresso sem NUNCA mostrar nenhuma versão do roteiro pro
        # usuário, nem a última (só reprovada internamente, nunca por um
        # humano). Último recurso: mostra o roteiro atual pra aprovação
        # humana em vez de insistir numa regeneração que o limite não
        # deixaria completar — melhor um humano decidir sobre algo
        # imperfeito do que a execução morrer sem mostrar nada.
        if len(tentativas_roteiro) >= 3:
            return Decisao(
                proxima_acao="CHAMAR_FERRAMENTA",
                nome_ferramenta="solicitar_aprovacao_humana",
                argumentos_ferramenta={
                    "peca": {
                        "tema": tema,
                        "slides": slides_atual,
                        "roteiro": roteiro_texto,
                        "formato": formato,
                    },
                    "etapa": "roteiro",
                },
                criterio_sucesso=(
                    "usuário decide aprovado=True/False pro roteiro — última "
                    "tentativa de gerar_roteiro já usada e a autocrítica ainda "
                    "não aprovou; melhor o humano decidir do que a execução "
                    "morrer sem mostrar nada"
                ),
            )

        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_roteiro",
            argumentos_ferramenta={
                "tema": tema,
                "perfil": perfil.as_dict(),
                # adaptação documentada: skills.md não tem campo de feedback
                # em gerar_roteiro, então o ajuste sugerido pela autocrítica
                # entra como mais um "insight anterior".
                "insights_anteriores": insights_recentes
                + [{"fonte": "autocritica_conteudo", "ajustes_sugeridos": ajustes}],
                "formato": formato,
                "temas_recentes": memoria.temas_recentes(limite=10),
            },
            criterio_sucesso="novo roteiro incorporando os ajustes da autocrítica",
        )

    # 5. solicitar_aprovacao_humana(etapa=roteiro) ---------------------
    aprovacoes_roteiro = [
        r for r in hist if r.get("ferramenta") == "solicitar_aprovacao_humana"
        and (r.get("argumentos") or {}).get("etapa") == "roteiro"
    ]
    aprovacao_roteiro_atual = None
    if aprovacoes_roteiro and (aprovacoes_roteiro[-1]["argumentos"].get("peca") or {}).get("roteiro") == roteiro_texto:
        aprovacao_roteiro_atual = aprovacoes_roteiro[-1]

    if aprovacao_roteiro_atual is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="solicitar_aprovacao_humana",
            argumentos_ferramenta={
                "peca": {
                    "tema": tema,
                    "slides": slides_atual,
                    "roteiro": roteiro_texto,
                    "formato": formato,
                },
                "etapa": "roteiro",
            },
            criterio_sucesso="usuário decide aprovado=True/False pro roteiro",
        )

    if not aprovacao_roteiro_atual["saida"].get("aprovado"):
        feedback = (aprovacao_roteiro_atual["saida"].get("feedback") or "").strip()
        if _pede_metricas(feedback):
            return Decisao(
                proxima_acao="PERGUNTAR_USUARIO",
                criterio_sucesso="usuário confirma entendimento do limite de escopo",
                pergunta=(
                    "O feedback menciona métricas/análise de desempenho, que estão "
                    "fora do escopo deste agente. Pode reformular o feedback focado "
                    "em roteiro/oferta/tom?"
                ),
            )
        if not feedback:
            return Decisao(
                proxima_acao="PERGUNTAR_USUARIO",
                criterio_sucesso="usuário fornece feedback específico o suficiente pra ajustar o roteiro",
                pergunta="O roteiro foi reprovado sem feedback. O que exatamente precisa mudar?",
            )

        # blindagem estrutural (mesmo padrão do branch de reprovação
        # interna, acima): incorporar esse feedback estouraria
        # chamadas_ferramenta.gerar_roteiro (rules.md: 3). Em vez de tentar
        # e morrer em sem_progresso, devolve o roteiro atual pra aprovação
        # humana de novo, com uma nota explicando que não há mais
        # tentativas automáticas — o usuário decide: aprova como está
        # (segue pro visual) ou continua reprovando (a execução para por
        # max_etapas_excedido, nunca por uma falha silenciosa).
        if len(tentativas_roteiro) >= 3:
            return Decisao(
                proxima_acao="CHAMAR_FERRAMENTA",
                nome_ferramenta="solicitar_aprovacao_humana",
                argumentos_ferramenta={
                    "peca": {
                        "tema": tema,
                        "slides": slides_atual,
                        "roteiro": roteiro_texto,
                        "formato": formato,
                        "nota": (
                            "As 3 tentativas de gerar_roteiro já foram usadas nesta "
                            "execução (rules.md) — esse feedback não pode mais ser "
                            "incorporado automaticamente. Aprove como está pra seguir "
                            "pra peça visual, ou reprove de novo se preferir abandonar "
                            "esta execução (ela vai parar por limite de etapas, sem "
                            "gerar um novo roteiro)."
                        ),
                    },
                    "etapa": "roteiro",
                },
                criterio_sucesso=(
                    "usuário decide aprovado=True/False pro roteiro — sem mais "
                    "tentativas de gerar_roteiro disponíveis"
                ),
            )

        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_roteiro",
            argumentos_ferramenta={
                "tema": tema,
                "perfil": perfil.as_dict(),
                "insights_anteriores": insights_recentes
                + [{"fonte": "feedback_humano_roteiro", "feedback": feedback}],
                "formato": formato,
                "temas_recentes": memoria.temas_recentes(limite=10),
            },
            criterio_sucesso="novo roteiro incorporando o feedback humano",
        )

    # roteiro aprovado ---------------------------------------------------
    memoria.guardar_memoria(
        execucao_id,
        "roteiro_aprovado",
        {"slides": slides_atual, "roteiro": roteiro_texto, "formato": formato},
    )

    slides_roteiro = slides_atual  # 1 peça visual por slide
    identidade_visual = perfil.identidade_visual
    # nome de arquivo de cada peça = {post_id}_slide{ordem}.png (agent.md).
    # o post_id da execução é o próprio execucao_id (ver ciclo.novo_execucao_id).
    post_id = execucao_id

    # -- estado da peça visual: geração, autocrítica e aprovação --------
    tentativas_visual = [
        r for r in hist if r.get("ferramenta") == "gerar_peca_visual"
        and (r.get("argumentos") or {}).get("slides") == slides_roteiro
    ]
    ultimo_visual = tentativas_visual[-1] if tentativas_visual else None

    if ultimo_visual is None:
        ids_evitar_historico = memoria.fotos_usadas_recentes(limite=50)
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_peca_visual",
            argumentos_ferramenta={
                "slides": slides_roteiro,
                "formato": formato,
                "identidade_visual": identidade_visual,
                "post_id": post_id,
                "ids_evitar_historico": ids_evitar_historico,
            },
            criterio_sucesso=(
                f"peça(s) visual(is) geradas — {len(slides_roteiro)} esperada(s), "
                "só após roteiro aprovado"
            ),
        )

    pecas_urls_atual = ultimo_visual["saida"].get("pecas_urls") or []

    # 7. autocritica_conteudo(tipo=visual) -- julga o conjunto de peças de
    # uma vez; as imagens reais vão anexadas por autocritica.py quando os
    # caminhos existem — ver ferramentas/autocritica.py.
    conteudo_visual_atual = "\n".join(pecas_urls_atual)
    autocriticas_visual = [
        r for r in hist if r.get("ferramenta") == "autocritica_conteudo"
        and (r.get("argumentos") or {}).get("tipo") == "visual"
    ]
    autocritica_visual_atual = None
    if autocriticas_visual and autocriticas_visual[-1]["argumentos"].get("conteudo") == conteudo_visual_atual:
        autocritica_visual_atual = autocriticas_visual[-1]

    if autocritica_visual_atual is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="autocritica_conteudo",
            argumentos_ferramenta={
                "conteudo": conteudo_visual_atual,
                "tipo": "visual",
                "criterios": _criterios_autocritica(perfil),
            },
            criterio_sucesso="reflection concluída: aprovado_internamente definido",
        )

    if not autocritica_visual_atual["saida"].get("aprovado_internamente"):
        ajustes = autocritica_visual_atual["saida"].get("ajustes_sugeridos", [])
        indices_com_problema = autocritica_visual_atual["saida"].get("indices_com_problema")

        # blindagem estrutural — defesa contra o prompt de autocritica.py um
        # dia deixar de seguir a instrução de nunca reprovar visual por
        # motivo de copy (ex: troca de modelo). `tentativas_visual` já reseta
        # sozinho quando o roteiro muda (só chega aqui sem ter passado pela
        # aprovação humana no meio — a única coisa que trocaria slides_roteiro
        # — então todas as tentativas contadas aqui são reprovações internas
        # seguidas pro MESMO roteiro). Depois de 2 reprovações internas
        # seguidas, a 3ª chamada — a última antes de esgotar
        # chamadas_ferramenta.gerar_peca_visual (rules.md: 3) — vai pro
        # gerar_roteiro em vez de insistir na peça visual, mesmo padrão já
        # usado na reprovação humana da etapa visual.
        if len(tentativas_visual) >= 2:
            # a escalada em si também tem orçamento limitado — se
            # chamadas_ferramenta.gerar_roteiro (rules.md: 3) já foi
            # esgotado (ex: o roteiro já passou por regenerações antes de
            # chegar aqui), escalar de novo só repetiria o bug original
            # (tentativa cega que o limite bloqueia, sem_progresso sem
            # mostrar nada). Não insiste em gerar_peca_visual (aceitar
            # mais tentativas cegas pra um problema que pode ser de texto
            # seria o mesmo erro) — mostra a peça atual pro humano decidir,
            # com uma nota explicando a situação.
            if len(tentativas_roteiro) >= 3:
                return Decisao(
                    proxima_acao="CHAMAR_FERRAMENTA",
                    nome_ferramenta="solicitar_aprovacao_humana",
                    argumentos_ferramenta={
                        "peca": {
                            "pecas_urls": pecas_urls_atual,
                            "formato": formato,
                            "nota": (
                                "A autocrítica reprovou esta peça 2 vezes seguidas e não "
                                "há mais tentativas de gerar_roteiro disponíveis nesta "
                                "execução (rules.md) pra corrigir se o problema for de "
                                "texto/copy. Revise com atenção antes de aprovar."
                            ),
                        },
                        "etapa": "visual",
                    },
                    criterio_sucesso=(
                        "usuário decide aprovado=True/False pra peça visual — sem mais "
                        "tentativas de gerar_roteiro disponíveis pra escalar"
                    ),
                )
            return Decisao(
                proxima_acao="CHAMAR_FERRAMENTA",
                nome_ferramenta="gerar_roteiro",
                argumentos_ferramenta={
                    "tema": tema,
                    "perfil": perfil.as_dict(),
                    "insights_anteriores": insights_recentes
                    + [{
                        "fonte": "autocritica_conteudo_visual_persistente",
                        "ajustes_sugeridos": ajustes,
                    }],
                    "formato": formato,
                    "temas_recentes": memoria.temas_recentes(limite=10),
                },
                criterio_sucesso=(
                    "novo roteiro como último recurso — autocrítica reprovou a peça "
                    "visual 2 vezes seguidas sem aprovar internamente; indício de que "
                    "o problema pode ser de texto, não de foto/layout"
                ),
            )

        argumentos_ferramenta: dict[str, Any] = {
            "slides": slides_roteiro,
            "formato": formato,
            "identidade_visual": identidade_visual,
            "post_id": post_id,
            "ajustes": ajustes,
            "ids_evitar_historico": memoria.fotos_usadas_recentes(limite=50),
        }
        if indices_com_problema and len(pecas_urls_atual) == len(slides_roteiro):
            # regenera só as peças apontadas, não o carrossel inteiro
            # (custo real — decisoes-de-engenharia.md, seção 2).
            # `indices_com_problema` é 1-based (autocritica.py/aprovacao_humana.py).
            argumentos_ferramenta["pecas_urls_existentes"] = pecas_urls_atual
            argumentos_ferramenta["indices_para_regenerar"] = indices_com_problema
            criterio_sucesso = (
                f"peça(s) {indices_com_problema} regenerada(s) incorporando os ajustes"
            )
        else:
            criterio_sucesso = "novo conjunto de peças incorporando os ajustes da autocrítica"

        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_peca_visual",
            argumentos_ferramenta=argumentos_ferramenta,
            criterio_sucesso=criterio_sucesso,
        )

    # 8. solicitar_aprovacao_humana(etapa=visual) -----------------------
    aprovacoes_visual = [
        r for r in hist if r.get("ferramenta") == "solicitar_aprovacao_humana"
        and (r.get("argumentos") or {}).get("etapa") == "visual"
    ]
    aprovacao_visual_atual = None
    if aprovacoes_visual and (aprovacoes_visual[-1]["argumentos"].get("peca") or {}).get("pecas_urls") == pecas_urls_atual:
        aprovacao_visual_atual = aprovacoes_visual[-1]

    if aprovacao_visual_atual is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="solicitar_aprovacao_humana",
            argumentos_ferramenta={
                "peca": {"pecas_urls": pecas_urls_atual, "formato": formato},
                "etapa": "visual",
            },
            criterio_sucesso="usuário decide aprovado=True/False pro conjunto de peças",
        )

    if not aprovacao_visual_atual["saida"].get("aprovado"):
        feedback = (aprovacao_visual_atual["saida"].get("feedback") or "").strip()
        if not feedback:
            return Decisao(
                proxima_acao="PERGUNTAR_USUARIO",
                criterio_sucesso="usuário fornece feedback específico o suficiente pra ajustar a peça visual",
                pergunta="A peça visual foi reprovada sem feedback. O que exatamente precisa mudar?",
            )
        # decisão revista: reprovação na etapa visual sempre volta pro
        # gerar_roteiro (nunca só pro gerar_peca_visual) — `ajustes` em
        # gerar_peca_visual só influencia a busca de foto, nunca o
        # titulo/corpo dos slides, então feedback sobre copy/headline (o
        # caso mais comum — só fica visível depois de renderizado) nunca
        # seria incorporado de verdade, e as tentativas se esgotavam contra
        # chamadas_ferramenta.gerar_peca_visual (rules.md) sem progresso
        # real. Reabre a aprovação do roteiro e, em seguida, a da peça
        # visual — mesmo padrão já usado na reprovação de roteiro.
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="gerar_roteiro",
            argumentos_ferramenta={
                "tema": tema,
                "perfil": perfil.as_dict(),
                "insights_anteriores": insights_recentes
                + [{"fonte": "feedback_humano_visual", "feedback": feedback}],
                "formato": formato,
                "temas_recentes": memoria.temas_recentes(limite=10),
            },
            criterio_sucesso="novo roteiro incorporando o feedback humano dado na etapa visual",
        )

    # peça visual aprovada — registrado na memória antes de liberar publicar_conteudo
    # (regra explícita de planner.md/rules.md: nunca por inferência).
    memoria.guardar_memoria(
        execucao_id,
        "roteiro_aprovado",
        {"pecas_urls": pecas_urls_atual, "status_aprovacao": "aprovado", "etapa": "visual"},
    )

    # 9. publicar_conteudo -----------------------------------------------
    resultado_publicacao = _ultimo(hist, "publicar_conteudo")
    if resultado_publicacao is None:
        return Decisao(
            proxima_acao="CHAMAR_FERRAMENTA",
            nome_ferramenta="publicar_conteudo",
            argumentos_ferramenta={
                "pecas_urls": pecas_urls_atual,
                "rede": perfil.rede or "instagram",
                # adaptação documentada: skills.md não separa "legenda" de
                # "roteiro" — usamos o roteiro aprovado (texto derivado dos
                # slides) como legenda.
                "legenda": roteiro_texto,
            },
            criterio_sucesso="status_publicacao=publicado retornado pelo adapter",
        )

    if resultado_publicacao["saida"].get("status") == "publicado":
        return Decisao(
            proxima_acao="FINALIZAR",
            criterio_sucesso="publicar_conteudo confirmado (status_publicacao=publicado)",
        )

    # publicação tentada e não confirmada (rules.md permite só 1 chamada
    # deste tipo no nível do planner — retries de rede já acontecem dentro
    # do executor). Escalar para o usuário em vez de inferir sucesso ou travar.
    return Decisao(
        proxima_acao="PERGUNTAR_USUARIO",
        criterio_sucesso="usuário decide como prosseguir após falha de publicação",
        pergunta=(
            f"publicar_conteudo não confirmou status=publicado (retornou "
            f"{resultado_publicacao['saida'].get('status')!r}). Quer tentar de novo, "
            f"publicar manualmente, ou encerrar?"
        ),
    )
