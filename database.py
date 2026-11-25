import json
import os
import sqlite3
from datetime import date
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "treino.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USAR_POSTGRES = bool(DATABASE_URL)

EXERCICIOS_INICIAIS = [
    {
        "nome": "Barra fixa pronada",
        "equipamento": "barra_porta",
        "musculos": {"costas": 1.0, "biceps": 0.5, "antebraco": 0.5},
    },
    {
        "nome": "Barra fixa supinada (chin-up)",
        "equipamento": "barra_porta",
        "musculos": {"costas": 0.8, "biceps": 1.0, "antebraco": 0.4},
    },
    {
        "nome": "Elevação de pernas na barra",
        "equipamento": "barra_porta",
        "musculos": {"abdomen": 1.0, "quadriceps": 0.3},
    },
    {
        "nome": "Flexão de braço tradicional",
        "equipamento": "colchonete",
        "musculos": {"peitoral": 1.0, "triceps": 0.5, "ombros": 0.5},
    },
    {
        "nome": "Flexão fechada (tríceps)",
        "equipamento": "colchonete",
        "musculos": {"triceps": 1.0, "peitoral": 0.6, "ombros": 0.4},
    },
    {
        "nome": "Agachamento livre",
        "equipamento": "colchonete",
        "musculos": {"quadriceps": 1.0, "gluteos": 0.8, "posteriores": 0.4},
    },
    {
        "nome": "Agachamento búlgaro",
        "equipamento": "colchonete",
        "musculos": {"quadriceps": 1.0, "gluteos": 1.0, "posteriores": 0.5},
    },
    {
        "nome": "Elevação pélvica (hip thrust)",
        "equipamento": "colchonete",
        "musculos": {"gluteos": 1.0, "posteriores": 0.7, "abdomen": 0.2},
    },
    {
        "nome": "Abdominal infra",
        "equipamento": "colchonete",
        "musculos": {"abdomen": 1.0},
    },
]


class CursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return getattr(self._cursor, "lastrowid", None)


class ConexaoAdapter:
    def __init__(self, conn, is_postgres: bool):
        self._conn = conn
        self.is_postgres = is_postgres

    def _adaptar_sql(self, sql: str) -> str:
        if not self.is_postgres:
            return sql
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple | list = ()) -> CursorAdapter:
        cur = self._conn.execute(self._adaptar_sql(sql), params)
        return CursorAdapter(cur)

    def executemany(self, sql: str, seq_params) -> CursorAdapter:
        cur = self._conn.executemany(self._adaptar_sql(sql), seq_params)
        return CursorAdapter(cur)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self._conn.close()


def conectar() -> ConexaoAdapter:
    if USAR_POSTGRES:
        if psycopg is None:
            raise RuntimeError(
                "psycopg não está instalado. Adicione 'psycopg[binary]' ao requirements.txt."
            )
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg.connect(url, row_factory=dict_row)
        return ConexaoAdapter(conn, is_postgres=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return ConexaoAdapter(conn, is_postgres=False)


def criar_tabelas(conn: ConexaoAdapter) -> None:
    if conn.is_postgres:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercicios (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL UNIQUE,
                equipamento TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pesos_musculares (
                id SERIAL PRIMARY KEY,
                exercicio_id INTEGER NOT NULL REFERENCES exercicios(id) ON DELETE CASCADE,
                grupo_muscular TEXT NOT NULL,
                peso REAL NOT NULL DEFAULT 1.0,
                UNIQUE (exercicio_id, grupo_muscular)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registros_treino (
                id SERIAL PRIMARY KEY,
                data_treino TEXT NOT NULL,
                exercicio_id INTEGER NOT NULL REFERENCES exercicios(id) ON DELETE CASCADE,
                serie INTEGER NOT NULL,
                repeticoes INTEGER NOT NULL,
                observacao TEXT DEFAULT '',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::text
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                equipamento TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pesos_musculares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exercicio_id INTEGER NOT NULL,
                grupo_muscular TEXT NOT NULL,
                peso REAL NOT NULL DEFAULT 1.0,
                FOREIGN KEY (exercicio_id) REFERENCES exercicios(id) ON DELETE CASCADE,
                UNIQUE (exercicio_id, grupo_muscular)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registros_treino (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_treino TEXT NOT NULL,
                exercicio_id INTEGER NOT NULL,
                serie INTEGER NOT NULL,
                repeticoes INTEGER NOT NULL,
                observacao TEXT DEFAULT '',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exercicio_id) REFERENCES exercicios(id) ON DELETE CASCADE
            )
            """
        )
    conn.commit()


def _inserir_exercicio_ignorar(conn: ConexaoAdapter, nome: str, equipamento: str) -> None:
    if conn.is_postgres:
        conn.execute(
            """
            INSERT INTO exercicios (nome, equipamento)
            VALUES (?, ?)
            ON CONFLICT (nome) DO NOTHING
            """,
            (nome, equipamento),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO exercicios (nome, equipamento)
            VALUES (?, ?)
            """,
            (nome, equipamento),
        )


def _inserir_peso_ignorar(
    conn: ConexaoAdapter, exercicio_id: int, musculo: str, peso: float
) -> None:
    if conn.is_postgres:
        conn.execute(
            """
            INSERT INTO pesos_musculares (exercicio_id, grupo_muscular, peso)
            VALUES (?, ?, ?)
            ON CONFLICT (exercicio_id, grupo_muscular) DO NOTHING
            """,
            (exercicio_id, musculo, peso),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO pesos_musculares (exercicio_id, grupo_muscular, peso)
            VALUES (?, ?, ?)
            """,
            (exercicio_id, musculo, peso),
        )


def popular_exercicios_iniciais(conn: ConexaoAdapter) -> None:
    nomes_removidos = (
        "Prancha abdominal",
        "Flexão declinada (pés elevados)",
    )
    conn.executemany(
        "DELETE FROM exercicios WHERE nome = ?",
        [(nome,) for nome in nomes_removidos],
    )
    for item in EXERCICIOS_INICIAIS:
        _inserir_exercicio_ignorar(conn, item["nome"], item["equipamento"])
        row = conn.execute(
            "SELECT id FROM exercicios WHERE nome = ?", (item["nome"],)
        ).fetchone()
        exercicio_id = row["id"]

        for musculo, peso in item["musculos"].items():
            _inserir_peso_ignorar(conn, exercicio_id, musculo, peso)
    conn.commit()


def inicializar_banco() -> None:
    with conectar() as conn:
        criar_tabelas(conn)
        popular_exercicios_iniciais(conn)


def listar_exercicios() -> list[dict]:
    with conectar() as conn:
        rows = conn.execute(
            "SELECT id, nome, equipamento FROM exercicios ORDER BY equipamento, nome"
        ).fetchall()
        return [dict(r) for r in rows]


def registrar_serie(
    exercicio_id: int,
    serie: int,
    repeticoes: int,
    data_treino: str | None = None,
    observacao: str = "",
) -> int:
    data_final = data_treino or date.today().isoformat()
    with conectar() as conn:
        if conn.is_postgres:
            row = conn.execute(
                """
                INSERT INTO registros_treino
                    (data_treino, exercicio_id, serie, repeticoes, observacao)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (data_final, exercicio_id, serie, repeticoes, observacao.strip()),
            ).fetchone()
            conn.commit()
            return int(row["id"])

        cursor = conn.execute(
            """
            INSERT INTO registros_treino
                (data_treino, exercicio_id, serie, repeticoes, observacao)
            VALUES (?, ?, ?, ?, ?)
            """,
            (data_final, exercicio_id, serie, repeticoes, observacao.strip()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def listar_registros(limite: int = 200) -> list[dict]:
    with conectar() as conn:
        rows = conn.execute(
            """
            SELECT
                rt.id,
                rt.data_treino,
                rt.serie,
                rt.repeticoes,
                rt.observacao,
                e.id AS exercicio_id,
                e.nome AS exercicio_nome,
                e.equipamento
            FROM registros_treino rt
            JOIN exercicios e ON e.id = rt.exercicio_id
            ORDER BY rt.data_treino DESC, rt.id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
        return [dict(r) for r in rows]


def buscar_registro(registro_id: int) -> dict | None:
    with conectar() as conn:
        row = conn.execute(
            """
            SELECT id, data_treino, exercicio_id, serie, repeticoes, observacao
            FROM registros_treino
            WHERE id = ?
            """,
            (registro_id,),
        ).fetchone()
        return dict(row) if row else None


def atualizar_registro(
    registro_id: int,
    exercicio_id: int,
    serie: int,
    repeticoes: int,
    data_treino: str,
    observacao: str = "",
) -> None:
    with conectar() as conn:
        conn.execute(
            """
            UPDATE registros_treino
            SET data_treino = ?,
                exercicio_id = ?,
                serie = ?,
                repeticoes = ?,
                observacao = ?
            WHERE id = ?
            """,
            (data_treino, exercicio_id, serie, repeticoes, observacao.strip(), registro_id),
        )
        conn.commit()


def excluir_registro(registro_id: int) -> None:
    with conectar() as conn:
        conn.execute("DELETE FROM registros_treino WHERE id = ?", (registro_id,))
        conn.commit()


def cadastrar_exercicio(
    nome: str,
    equipamento: str,
    musculos_pesos: dict[str, float],
) -> int:
    nome_limpo = nome.strip()
    equip_limpo = equipamento.strip()
    with conectar() as conn:
        _inserir_exercicio_ignorar(conn, nome_limpo, equip_limpo)
        row = conn.execute(
            "SELECT id FROM exercicios WHERE nome = ?", (nome_limpo,)
        ).fetchone()
        exercicio_id = int(row["id"])

        for grupo, peso in musculos_pesos.items():
            if peso > 0:
                if conn.is_postgres:
                    conn.execute(
                        """
                        INSERT INTO pesos_musculares (exercicio_id, grupo_muscular, peso)
                        VALUES (?, ?, ?)
                        ON CONFLICT (exercicio_id, grupo_muscular)
                        DO UPDATE SET peso = EXCLUDED.peso
                        """,
                        (exercicio_id, grupo, float(peso)),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO pesos_musculares (exercicio_id, grupo_muscular, peso)
                        VALUES (?, ?, ?)
                        ON CONFLICT(exercicio_id, grupo_muscular)
                        DO UPDATE SET peso = excluded.peso
                        """,
                        (exercicio_id, grupo, float(peso)),
                    )
        conn.commit()
        return exercicio_id


def exportar_backup_json() -> str:
    with conectar() as conn:
        exercicios = [
            dict(r) for r in conn.execute("SELECT * FROM exercicios").fetchall()
        ]
        pesos = [
            dict(r) for r in conn.execute("SELECT * FROM pesos_musculares").fetchall()
        ]
        registros = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM registros_treino ORDER BY id ASC"
            ).fetchall()
        ]

    payload = {
        "versao": 1,
        "exercicios": exercicios,
        "pesos_musculares": pesos,
        "registros_treino": registros,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def importar_backup_json(conteudo_json: str) -> int:
    dados = json.loads(conteudo_json)
    registros = dados.get("registros_treino", [])
    inseridos = 0

    with conectar() as conn:
        for ex in dados.get("exercicios", []):
            _inserir_exercicio_ignorar(conn, ex["nome"], ex["equipamento"])

        mapa_ids = {
            r["nome"]: r["id"]
            for r in conn.execute("SELECT id, nome FROM exercicios").fetchall()
        }

        id_antigo_para_nome = {
            ex["id"]: ex["nome"] for ex in dados.get("exercicios", [])
        }

        for reg in registros:
            nome_ex = id_antigo_para_nome.get(reg.get("exercicio_id"))
            novo_ex_id = mapa_ids.get(nome_ex)
            if not novo_ex_id:
                continue

            conn.execute(
                """
                INSERT INTO registros_treino
                    (data_treino, exercicio_id, serie, repeticoes, observacao, criado_em)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    reg["data_treino"],
                    novo_ex_id,
                    reg["serie"],
                    reg["repeticoes"],
                    reg.get("observacao", ""),
                    reg.get("criado_em", ""),
                ),
            )
            inseridos += 1

        conn.commit()
    return inseridos


if __name__ == "__main__":
    inicializar_banco()
    modo = "PostgreSQL" if USAR_POSTGRES else f"SQLite ({DB_PATH})"
    print(f"Banco inicializado em: {modo}")
    print(f"Exercícios cadastrados: {len(listar_exercicios())}")