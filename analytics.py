from collections import defaultdict
from datetime import date, timedelta

from database import conectar

GRUPOS_MUSCULARES_PADRAO = [
    "peitoral",
    "costas",
    "biceps",
    "triceps",
    "ombros",
    "quadriceps",
    "posteriores",
    "gluteos",
    "abdomen",
    "antebraco",
]


def volume_por_musculo(dias: int = 7) -> list[dict]:
    """
    Calcula o volume ponderado (repeticoes * peso) por grupo muscular
    nos últimos `dias` dias.
    """
    data_inicio = (date.today() - timedelta(days=max(dias - 1, 0))).isoformat()
    totais: dict[str, float] = {m: 0.0 for m in GRUPOS_MUSCULARES_PADRAO}
    series_por_musculo: dict[str, int] = defaultdict(int)

    with conectar() as conn:
        rows = conn.execute(
            """
            SELECT
                rt.repeticoes,
                pm.grupo_muscular,
                pm.peso
            FROM registros_treino rt
            JOIN pesos_musculares pm ON pm.exercicio_id = rt.exercicio_id
            WHERE rt.data_treino >= ?
            """,
            (data_inicio,),
        ).fetchall()

    for row in rows:
        musculo = row["grupo_muscular"]
        peso = float(row["peso"])
        reps = int(row["repeticoes"])
        totais[musculo] = totais.get(musculo, 0.0) + (reps * peso)
        series_por_musculo[musculo] += 1

    maior_volume = max(totais.values()) if totais else 0.0
    resultado = []

    for musculo, volume in totais.items():
        volume_arredondado = round(volume, 1)
        percentual_relativo = (
            round((volume / maior_volume) * 100) if maior_volume > 0 else 0
        )
        resultado.append(
            {
                "grupo_muscular": musculo,
                "volume": volume_arredondado,
                "series_ponderadas": series_por_musculo[musculo],
                "percentual_relativo": percentual_relativo,
            }
        )

    resultado.sort(key=lambda item: (-item["volume"], item["grupo_muscular"]))
    return resultado


def progresso_por_exercicio() -> list[dict]:
    """
    Retorna recorde de repetições, total de séries e total de repetições
    por exercício cadastrado.
    """
    with conectar() as conn:
        rows = conn.execute(
            """
            SELECT
                e.id AS exercicio_id,
                e.nome AS exercicio_nome,
                e.equipamento,
                COUNT(rt.id) AS total_series,
                COALESCE(SUM(rt.repeticoes), 0) AS total_repeticoes,
                COALESCE(MAX(rt.repeticoes), 0) AS recorde_repeticoes,
                MAX(rt.data_treino) AS ultimo_treino
            FROM exercicios e
            LEFT JOIN registros_treino rt ON rt.exercicio_id = e.id
            GROUP BY e.id, e.nome, e.equipamento
            ORDER BY total_series DESC, e.nome ASC
            """
        ).fetchall()

    return [dict(r) for r in rows]


def resumo_geral(dias: int = 7) -> dict:
    data_inicio = (date.today() - timedelta(days=max(dias - 1, 0))).isoformat()
    with conectar() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_series,
                COALESCE(SUM(repeticoes), 0) AS total_repeticoes,
                COUNT(DISTINCT data_treino) AS dias_treinados
            FROM registros_treino
            WHERE data_treino >= ?
            """,
            (data_inicio,),
        ).fetchone()

    musculos = volume_por_musculo(dias=dias)
    com_volume = [m for m in musculos if m["volume"] > 0]
    mais_trabalhado = com_volume[0] if com_volume else None
    menos_trabalhado = com_volume[-1] if len(com_volume) > 1 else None

    return {
        "dias": dias,
        "total_series": int(row["total_series"]),
        "total_repeticoes": int(row["total_repeticoes"]),
        "dias_treinados": int(row["dias_treinados"]),
        "mais_trabalhado": mais_trabalhado,
        "menos_trabalhado": menos_trabalhado,
    }


if __name__ == "__main__":
    from database import inicializar_banco, registrar_serie

    inicializar_banco()
    # Exemplo rápido de teste se ainda não houver registros
    if resumo_geral(dias=7)["total_series"] == 0:
        registrar_serie(exercicio_id=1, serie=1, repeticoes=3, observacao="Teste")
        registrar_serie(exercicio_id=4, serie=1, repeticoes=10, observacao="Teste")

    print("Resumo (7 dias):", resumo_geral(dias=7))
    print("Volume por músculo:")
    for item in volume_por_musculo(dias=7):
        print(f"  {item['grupo_muscular']:12s} -> {item['volume']:5.1f} ({item['percentual_relativo']}%)")