"""memoria.py — Repository de persistência (implementa memory.md + a seção 3
de decisoes-de-engenharia.md).

Todo acesso a banco do runtime passa por `MemoriaRepository`. Nenhum outro
módulo deve abrir o SQLite diretamente (decisão registrada em
decisoes-de-engenharia.md, seção 3 — troca futura para Postgres, e ponto de
handoff com o agente-analista-metricas via as tabelas `posts`/`insights`).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Campos que memory.md manda guardar na memória curta. Qualquer `tipo` fora
# desta lista ainda é aceito (não é um contrato fechado sobre o schema), mas
# esses são os nomes usados pelo restante do runtime.
TIPOS_GUARDAVEIS = {
    "resultado_de_ferramenta",
    "decisao_do_planejador",
    "insights_recebidos",
    "evidencia_coletada",
    "roteiro_aprovado",
    "feedback_de_aprovacao",
    # tema escolhido pelo planejador a partir de temas_sugeridos quando o
    # agente roda sem --entrada (planner.md/comandos.md) — equivale a um
    # --entrada explícito daí pra frente.
    "tema_escolhido",
}

MAX_REGISTROS_MEMORIA_CURTA = 40  # memory.md: memoria_curta.max_registros

# Tipos que a poda de max_registros NUNCA descarta: o planejador reconstrói
# todo o estado do ciclo a partir deles (replay), e `executor._verificar_limites`
# conta `resultado_de_ferramenta` pra impor `rules.md: chamadas_ferramenta`.
# Podar essas linhas faria o planejador re-executar etapas e os limites
# cumulativos subcontarem — crítico agora que uma execução pode ser
# suspensa/retomada várias vezes (componente front-end). memory.md fala em
# "tipos descartáveis"; esta é a lista do que NÃO é.
TIPOS_NAO_DESCARTAVEIS = frozenset({"resultado_de_ferramenta", "tema_escolhido"})


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RegistroMemoria:
    id: int | None
    execucao_id: str
    tipo: str
    conteudo: dict[str, Any]
    criado_em: str = field(default_factory=_agora_iso)


class MemoriaRepository(ABC):
    """Interface de persistência. Trocar SQLite por outro banco significa
    implementar esta interface de novo — nada mais no runtime muda."""

    # -- memória curta (memory.md) ------------------------------------
    @abstractmethod
    def guardar_memoria(self, execucao_id: str, tipo: str, conteudo: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def guardar_memoria_unica(
        self, execucao_id: str, tipo: str, conteudo: dict[str, Any]
    ) -> None:
        """Idempotente: no-op se já há linha idêntica (execucao_id+tipo+conteudo)."""
        ...

    @abstractmethod
    def listar_memoria(self, execucao_id: str, tipo: str | None = None) -> list[RegistroMemoria]:
        ...

    # -- tabela posts (decisoes-de-engenharia.md, seção 3) -------------
    @abstractmethod
    def upsert_post(self, post: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def buscar_post(self, post_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def listar_posts(self, limite: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Histórico de posts, mais recentes primeiro. Usado pela casca HTTP
        (api/) que expõe o histórico pro front-end — o runtime em si não
        precisa listar posts, só faz upsert/buscar por id."""
        ...

    # -- tabela insights (escrita pelo agente-analista-metricas) -------
    @abstractmethod
    def buscar_insights_recentes(self, limite: int) -> list[dict[str, Any]]:
        ...

    # -- resumo final (memory.md: resumo_final) ------------------------
    @abstractmethod
    def salvar_resumo_final(self, execucao_id: str, resumo: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def buscar_resumo_final(self, execucao_id: str) -> dict[str, Any] | None:
        ...

    # -- cache (decisoes-de-engenharia.md, seção 4: cache curto só em
    # pesquisar_tendencias_nicho) — extensão de engenharia, não faz parte
    # de nenhum contrato de saída; vive atrás do Repository como tudo mais
    # que toca o banco.
    @abstractmethod
    def obter_cache(self, chave: str) -> dict[str, Any] | None:
        """None se não existir ou se tiver expirado."""
        ...

    @abstractmethod
    def salvar_cache(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        ...

    # -- fila de aprovação (Etapa 2 do componente front-end) -----------
    # Tabelas `aprovacoes` e `execucao_ativa`: existem pra a casca HTTP
    # (api/) transformar o passo de aprovação síncrono num fluxo assíncrono
    # sem tocar na lógica de decisão do planejador. O CLI não usa nada disso.
    @abstractmethod
    def registrar_aprovacao_pendente(
        self, *, execucao_id: str, etapa: str, chave_peca: str, peca: dict[str, Any]
    ) -> str:
        """Idempotente por (execucao_id, etapa, chave_peca). Retorna o id."""
        ...

    @abstractmethod
    def buscar_aprovacao(
        self, execucao_id: str, etapa: str, chave_peca: str
    ) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def buscar_aprovacao_por_id(self, aprovacao_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def listar_aprovacoes_pendentes(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def registrar_decisao_aprovacao(
        self, aprovacao_id: str, *, aprovado: bool, feedback: str, decidido_por: str
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def criar_execucao_ativa(self, execucao_id: str, *, entrada: str | None, formato: str) -> None:
        ...

    @abstractmethod
    def atualizar_execucao_ativa(
        self,
        execucao_id: str,
        *,
        estado: str | None = None,
        segundos_ativos: float | None = None,
        motivo_parada: str | None = None,
        pergunta_aberta: str | None = None,
    ) -> None:
        ...

    @abstractmethod
    def buscar_execucao_ativa(self, execucao_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def execucao_em_andamento(self) -> dict[str, Any] | None:
        """A execução em estado 'rodando', 'suspensa' ou
        'aguardando_intervencao', se houver (v1: no máximo uma — 1 instância
        = 1 tenant). 'aguardando_intervencao' também segura a trava — o
        cliente precisa descartar ou o operador precisa corrigir a causa
        antes de um novo disparo fazer sentido."""
        ...

    @abstractmethod
    def listar_execucoes_aguardando_intervencao(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def descartar_execucao(self, execucao_id: str, *, por: str) -> dict[str, Any]:
        """Move a execução pra estado terminal 'descartada' e cancela
        aprovações pendentes órfãs. Levanta KeyError (não existe) ou
        ValueError (está 'rodando', ou já 'descartada') — quem chama decide
        404/409."""
        ...

    @abstractmethod
    def registrar_disparo_execucao(self, *, execucao_id: str, origem: str) -> None:
        ...

    @abstractmethod
    def contar_disparos_desde(self, desde_iso: str) -> int:
        ...

    # -- mídia (api/rotas/pecas.py — Etapa 3) --------------------------
    @abstractmethod
    def peca_registrada(self, nome_arquivo: str) -> bool:
        """True se `nome_arquivo` corresponde a uma peça visual REGISTRADA
        (em `posts`, em `aprovacoes` etapa=visual/publicacao, ou em
        resultado_de_ferramenta de `gerar_peca_visual` de alguma execução)
        — não só "existe um arquivo com esse nome no disco". Usado pela
        rota que serve a imagem: nunca serve algo que não veio do próprio
        pipeline do agente."""
        ...


class SQLiteMemoriaRepository(MemoriaRepository):
    """Implementação v1 (decisoes-de-engenharia.md, seção 3)."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # timeout: a casca HTTP (api/) roda o ciclo num thread e atende
        # requests noutro — os dois abrem o banco. WAL + busy_timeout deixam
        # leitura concorrente com uma escrita sem "database is locked". Sem
        # efeito prático pro CLI (um processo só).
        self._conn = sqlite3.connect(self._db_path, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._criar_schema()

    def _criar_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memoria_curta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execucao_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                criado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memoria_execucao
                ON memoria_curta (execucao_id, tipo);

            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                tema TEXT,
                roteiro TEXT,
                peca_url TEXT,
                rede TEXT,
                status_aprovacao TEXT,
                status_publicacao TEXT,
                publicado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                insight TEXT,
                recomendacao TEXT,
                gerado_por TEXT,
                gerado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS resumos_finais (
                execucao_id TEXT PRIMARY KEY,
                resumo TEXT NOT NULL,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cache (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                expira_em TEXT NOT NULL
            );

            -- fila de aprovação (casca HTTP / componente front-end) --------
            CREATE TABLE IF NOT EXISTS aprovacoes (
                id TEXT PRIMARY KEY,
                execucao_id TEXT NOT NULL,
                etapa TEXT NOT NULL,            -- roteiro | visual | publicacao
                chave_peca TEXT NOT NULL,       -- hash do conteúdo submetido
                peca_json TEXT NOT NULL,        -- snapshot p/ a UI renderizar
                estado TEXT NOT NULL,           -- pendente | decidida
                aprovado INTEGER,              -- NULL enquanto pendente
                feedback TEXT,
                decidido_por TEXT,
                criado_em TEXT NOT NULL,
                decidido_em TEXT,
                UNIQUE (execucao_id, etapa, chave_peca)
            );
            CREATE INDEX IF NOT EXISTS idx_aprovacoes_estado ON aprovacoes (estado);

            CREATE TABLE IF NOT EXISTS execucao_ativa (
                execucao_id TEXT PRIMARY KEY,
                -- rodando | suspensa | aguardando_intervencao | finalizada | erro | descartada
                estado TEXT NOT NULL,
                entrada TEXT,
                formato TEXT,
                segundos_ativos REAL NOT NULL DEFAULT 0,  -- exclui espera humana
                motivo_parada TEXT,
                pergunta_aberta TEXT,          -- texto do PERGUNTAR_USUARIO no modo fila
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS disparos_execucao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execucao_id TEXT NOT NULL,
                origem TEXT,
                criado_em TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_disparos_criado ON disparos_execucao (criado_em);
            """
        )
        self._conn.commit()
        self._migrar_colunas_novas()

    def _migrar_colunas_novas(self) -> None:
        """CREATE TABLE IF NOT EXISTS não adiciona coluna em banco já criado
        por uma versão anterior do schema — migração idempotente mínima."""
        colunas = {row[1] for row in self._conn.execute("PRAGMA table_info(execucao_ativa)")}
        if "pergunta_aberta" not in colunas:
            self._conn.execute("ALTER TABLE execucao_ativa ADD COLUMN pergunta_aberta TEXT")
            self._conn.commit()

    # -- memória curta ---------------------------------------------------
    def guardar_memoria(self, execucao_id: str, tipo: str, conteudo: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO memoria_curta (execucao_id, tipo, conteudo, criado_em) VALUES (?, ?, ?, ?)",
            (execucao_id, tipo, json.dumps(conteudo, ensure_ascii=False), _agora_iso()),
        )
        self._conn.commit()
        self._aplicar_max_registros(execucao_id)

    def _aplicar_max_registros(self, execucao_id: str) -> None:
        """memory.md: max_registros: 40 — descarta os mais antigos além do
        limite, mas SÓ entre os tipos descartáveis (ver
        TIPOS_NAO_DESCARTAVEIS). O total é contado sobre a memória inteira;
        a poda recai apenas nos tipos de bookkeeping."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM memoria_curta WHERE execucao_id = ?", (execucao_id,)
        ).fetchone()[0]
        excedente = total - MAX_REGISTROS_MEMORIA_CURTA
        if excedente <= 0:
            return
        marcadores = ", ".join("?" for _ in TIPOS_NAO_DESCARTAVEIS)
        ids_antigos = self._conn.execute(
            f"SELECT id FROM memoria_curta WHERE execucao_id = ? "
            f"AND tipo NOT IN ({marcadores}) ORDER BY id ASC LIMIT ?",
            (execucao_id, *TIPOS_NAO_DESCARTAVEIS, excedente),
        ).fetchall()
        if ids_antigos:
            self._conn.executemany(
                "DELETE FROM memoria_curta WHERE id = ?", [(row["id"],) for row in ids_antigos]
            )
            self._conn.commit()

    def guardar_memoria_unica(
        self, execucao_id: str, tipo: str, conteudo: dict[str, Any]
    ) -> None:
        """Como guardar_memoria, mas no-op se já existe uma linha idêntica
        (mesmo execucao_id+tipo+conteudo). Usado em registros determinísticos
        de bookkeeping (`roteiro_aprovado`, `decisao_do_planejador`) que o
        replay de uma retomada re-derivaria e re-gravaria à toa."""
        alvo = json.dumps(conteudo, ensure_ascii=False)
        existe = self._conn.execute(
            "SELECT 1 FROM memoria_curta WHERE execucao_id = ? AND tipo = ? AND conteudo = ? LIMIT 1",
            (execucao_id, tipo, alvo),
        ).fetchone()
        if existe:
            return
        self.guardar_memoria(execucao_id, tipo, conteudo)

    def listar_memoria(self, execucao_id: str, tipo: str | None = None) -> list[RegistroMemoria]:
        if tipo is None:
            rows = self._conn.execute(
                "SELECT * FROM memoria_curta WHERE execucao_id = ? ORDER BY id ASC",
                (execucao_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memoria_curta WHERE execucao_id = ? AND tipo = ? ORDER BY id ASC",
                (execucao_id, tipo),
            ).fetchall()
        return [
            RegistroMemoria(
                id=row["id"],
                execucao_id=row["execucao_id"],
                tipo=row["tipo"],
                conteudo=json.loads(row["conteudo"]),
                criado_em=row["criado_em"],
            )
            for row in rows
        ]

    # -- posts -------------------------------------------------------
    def upsert_post(self, post: dict[str, Any]) -> None:
        campos = (
            "post_id",
            "tema",
            "roteiro",
            "peca_url",
            "rede",
            "status_aprovacao",
            "status_publicacao",
            "publicado_em",
        )
        post = dict(post)
        # decisão revista (skills.md: gerar_peca_visual): carrossel de
        # verdade tem várias peças — a coluna `peca_url` (TEXT) guarda a
        # lista serializada em JSON em vez de mudar o schema da tabela.
        if isinstance(post.get("peca_url"), list):
            post["peca_url"] = json.dumps(post["peca_url"], ensure_ascii=False)
        valores = tuple(post.get(c) for c in campos)
        placeholders = ", ".join("?" for _ in campos)
        atualizacoes = ", ".join(f"{c}=excluded.{c}" for c in campos if c != "post_id")
        self._conn.execute(
            f"INSERT INTO posts ({', '.join(campos)}) VALUES ({placeholders}) "
            f"ON CONFLICT(post_id) DO UPDATE SET {atualizacoes}",
            valores,
        )
        self._conn.commit()

    def buscar_post(self, post_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None
        return self._post_from_row(row)

    def listar_posts(self, limite: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        # publicado_em é ISO-8601 UTC (ordenação lexicográfica == cronológica);
        # NULLs (posts não publicados) vão pro fim.
        rows = self._conn.execute(
            "SELECT * FROM posts ORDER BY publicado_em IS NULL, publicado_em DESC, post_id DESC "
            "LIMIT ? OFFSET ?",
            (limite, offset),
        ).fetchall()
        return [self._post_from_row(row) for row in rows]

    @staticmethod
    def _post_from_row(row: sqlite3.Row) -> dict[str, Any]:
        post = dict(row)
        if post.get("peca_url"):
            try:
                post["peca_url"] = json.loads(post["peca_url"])
            except (json.JSONDecodeError, TypeError):
                pass  # posts antigos (v1, antes do carrossel) guardavam string simples
        return post

    # -- insights (lidos aqui; escritos pelo agente-analista-metricas) --
    def buscar_insights_recentes(self, limite: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM insights ORDER BY gerado_em DESC LIMIT ?", (limite,)
        ).fetchall()
        return [dict(row) for row in rows]

    # -- resumo final --------------------------------------------------
    def salvar_resumo_final(self, execucao_id: str, resumo: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO resumos_finais (execucao_id, resumo, criado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(execucao_id) DO UPDATE SET resumo=excluded.resumo, criado_em=excluded.criado_em",
            (execucao_id, json.dumps(resumo, ensure_ascii=False), _agora_iso()),
        )
        self._conn.commit()

    def buscar_resumo_final(self, execucao_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT resumo FROM resumos_finais WHERE execucao_id = ?", (execucao_id,)
        ).fetchone()
        return json.loads(row["resumo"]) if row else None

    # -- cache ---------------------------------------------------------
    def obter_cache(self, chave: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT valor, expira_em FROM cache WHERE chave = ?", (chave,)
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row["expira_em"]) < datetime.now(timezone.utc):
            self._conn.execute("DELETE FROM cache WHERE chave = ?", (chave,))
            self._conn.commit()
            return None
        return json.loads(row["valor"])

    def salvar_cache(self, chave: str, valor: dict[str, Any], ttl_segundos: int) -> None:
        from datetime import timedelta

        expira_em = (datetime.now(timezone.utc) + timedelta(seconds=ttl_segundos)).isoformat()
        self._conn.execute(
            "INSERT INTO cache (chave, valor, expira_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, expira_em=excluded.expira_em",
            (chave, json.dumps(valor, ensure_ascii=False), expira_em),
        )
        self._conn.commit()

    # -- fila de aprovação -------------------------------------------------
    @staticmethod
    def _aprovacao_from_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["peca"] = json.loads(d.pop("peca_json"))
        d["aprovado"] = None if d["aprovado"] is None else bool(d["aprovado"])
        return d

    def registrar_aprovacao_pendente(
        self, *, execucao_id: str, etapa: str, chave_peca: str, peca: dict[str, Any]
    ) -> str:
        existente = self.buscar_aprovacao(execucao_id, etapa, chave_peca)
        if existente is not None:
            return existente["id"]
        novo_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO aprovacoes (id, execucao_id, etapa, chave_peca, peca_json, "
            "estado, criado_em) VALUES (?, ?, ?, ?, ?, 'pendente', ?)",
            (novo_id, execucao_id, etapa, chave_peca,
             json.dumps(peca, ensure_ascii=False), _agora_iso()),
        )
        self._conn.commit()
        return novo_id

    def buscar_aprovacao(
        self, execucao_id: str, etapa: str, chave_peca: str
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM aprovacoes WHERE execucao_id = ? AND etapa = ? AND chave_peca = ?",
            (execucao_id, etapa, chave_peca),
        ).fetchone()
        return self._aprovacao_from_row(row) if row else None

    def buscar_aprovacao_por_id(self, aprovacao_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM aprovacoes WHERE id = ?", (aprovacao_id,)
        ).fetchone()
        return self._aprovacao_from_row(row) if row else None

    def listar_aprovacoes_pendentes(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM aprovacoes WHERE estado = 'pendente' ORDER BY criado_em ASC"
        ).fetchall()
        return [self._aprovacao_from_row(r) for r in rows]

    def registrar_decisao_aprovacao(
        self, aprovacao_id: str, *, aprovado: bool, feedback: str, decidido_por: str
    ) -> dict[str, Any]:
        cur = self._conn.execute(
            "UPDATE aprovacoes SET estado = 'decidida', aprovado = ?, feedback = ?, "
            "decidido_por = ?, decidido_em = ? WHERE id = ? AND estado = 'pendente'",
            (1 if aprovado else 0, feedback, decidido_por, _agora_iso(), aprovacao_id),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            atual = self.buscar_aprovacao_por_id(aprovacao_id)
            if atual is None:
                raise KeyError(f"aprovação {aprovacao_id} não existe")
            raise ValueError(f"aprovação {aprovacao_id} já está '{atual['estado']}'")
        resultado = self.buscar_aprovacao_por_id(aprovacao_id)
        assert resultado is not None
        return resultado

    # -- execução ativa --------------------------------------------------
    def criar_execucao_ativa(
        self, execucao_id: str, *, entrada: str | None, formato: str
    ) -> None:
        agora = _agora_iso()
        self._conn.execute(
            "INSERT INTO execucao_ativa (execucao_id, estado, entrada, formato, "
            "segundos_ativos, criado_em, atualizado_em) "
            "VALUES (?, 'rodando', ?, ?, 0, ?, ?) "
            "ON CONFLICT(execucao_id) DO UPDATE SET estado='rodando', entrada=excluded.entrada, "
            "formato=excluded.formato, atualizado_em=excluded.atualizado_em",
            (execucao_id, entrada, formato, agora, agora),
        )
        self._conn.commit()

    def atualizar_execucao_ativa(
        self,
        execucao_id: str,
        *,
        estado: str | None = None,
        segundos_ativos: float | None = None,
        motivo_parada: str | None = None,
        pergunta_aberta: str | None = None,
    ) -> None:
        campos: list[str] = ["atualizado_em = ?"]
        valores: list[Any] = [_agora_iso()]
        if estado is not None:
            campos.append("estado = ?")
            valores.append(estado)
        if segundos_ativos is not None:
            campos.append("segundos_ativos = ?")
            valores.append(segundos_ativos)
        if motivo_parada is not None:
            campos.append("motivo_parada = ?")
            valores.append(motivo_parada)
        if pergunta_aberta is not None:
            campos.append("pergunta_aberta = ?")
            valores.append(pergunta_aberta)
        valores.append(execucao_id)
        self._conn.execute(
            f"UPDATE execucao_ativa SET {', '.join(campos)} WHERE execucao_id = ?", valores
        )
        self._conn.commit()

    def buscar_execucao_ativa(self, execucao_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM execucao_ativa WHERE execucao_id = ?", (execucao_id,)
        ).fetchone()
        return dict(row) if row else None

    def execucao_em_andamento(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM execucao_ativa "
            "WHERE estado IN ('rodando', 'suspensa', 'aguardando_intervencao') "
            "ORDER BY atualizado_em DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def listar_execucoes_aguardando_intervencao(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM execucao_ativa WHERE estado = 'aguardando_intervencao' "
            "ORDER BY atualizado_em ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def descartar_execucao(self, execucao_id: str, *, por: str) -> dict[str, Any]:
        atual = self.buscar_execucao_ativa(execucao_id)
        if atual is None:
            raise KeyError(f"execução {execucao_id} não existe")
        if atual["estado"] == "rodando":
            raise ValueError(f"execução {execucao_id} está 'rodando' — não dá pra descartar")
        if atual["estado"] == "descartada":
            raise ValueError(f"execução {execucao_id} já está 'descartada'")

        agora = _agora_iso()
        self._conn.execute(
            "UPDATE execucao_ativa SET estado = 'descartada', "
            "motivo_parada = 'descartada_pelo_operador', atualizado_em = ? "
            "WHERE execucao_id = ?",
            (agora, execucao_id),
        )
        # limpa pendência órfã — senão continuaria aparecendo na fila pra
        # uma execução que ninguém vai mais retomar.
        self._conn.execute(
            "UPDATE aprovacoes SET estado = 'cancelada', decidido_por = ?, decidido_em = ? "
            "WHERE execucao_id = ? AND estado = 'pendente'",
            (por, agora, execucao_id),
        )
        self._conn.commit()
        resultado = self.buscar_execucao_ativa(execucao_id)
        assert resultado is not None
        return resultado

    # -- disparos (rate limit local — 2ª camada) ------------------------
    def registrar_disparo_execucao(self, *, execucao_id: str, origem: str) -> None:
        self._conn.execute(
            "INSERT INTO disparos_execucao (execucao_id, origem, criado_em) VALUES (?, ?, ?)",
            (execucao_id, origem, _agora_iso()),
        )
        self._conn.commit()

    def contar_disparos_desde(self, desde_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM disparos_execucao WHERE criado_em >= ?", (desde_iso,)
        ).fetchone()
        return int(row[0])

    # -- mídia -----------------------------------------------------------
    def peca_registrada(self, nome_arquivo: str) -> bool:
        def _bate(caminho_bruto: Any) -> bool:
            if not isinstance(caminho_bruto, str):
                return False
            # basename puro — funciona pra path absoluto, relativo, ou já
            # reescrito como "/pecas/<nome>" (ver api/media.py).
            return caminho_bruto.rsplit("/", 1)[-1] == nome_arquivo

        filtro = f"%{nome_arquivo}%"

        # 1) posts.peca_url (json list, ou string legada de antes do carrossel)
        for (bruto,) in self._conn.execute(
            "SELECT peca_url FROM posts WHERE peca_url LIKE ?", (filtro,)
        ):
            try:
                valores = json.loads(bruto)
            except (json.JSONDecodeError, TypeError):
                valores = bruto
            valores = valores if isinstance(valores, list) else [valores]
            if any(_bate(v) for v in valores):
                return True

        # 2) aprovacoes.peca_json — etapa visual ({"pecas_urls":[...]}) ou
        # publicacao ({"argumentos": {"pecas_urls":[...]}})
        for (bruto,) in self._conn.execute(
            "SELECT peca_json FROM aprovacoes WHERE etapa IN ('visual','publicacao') "
            "AND peca_json LIKE ?",
            (filtro,),
        ):
            try:
                peca = json.loads(bruto)
            except (json.JSONDecodeError, TypeError):
                continue
            candidatos = list(peca.get("pecas_urls") or [])
            candidatos += list((peca.get("argumentos") or {}).get("pecas_urls") or [])
            if any(_bate(v) for v in candidatos):
                return True

        # 3) memoria_curta — resultado de gerar_peca_visual de qualquer
        # execução (cobre pendências ainda não decididas / não finalizadas
        # como post). LIKE já filtra pelo nome no texto bruto do JSON antes
        # de desserializar, então não varre tudo.
        for (bruto,) in self._conn.execute(
            "SELECT conteudo FROM memoria_curta WHERE tipo = 'resultado_de_ferramenta' "
            "AND conteudo LIKE '%gerar_peca_visual%' AND conteudo LIKE ?",
            (filtro,),
        ):
            try:
                c = json.loads(bruto)
            except (json.JSONDecodeError, TypeError):
                continue
            if c.get("ferramenta") != "gerar_peca_visual":
                continue
            if any(_bate(v) for v in (c.get("saida") or {}).get("pecas_urls") or []):
                return True

        return False

    def close(self) -> None:
        self._conn.close()
