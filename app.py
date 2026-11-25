import os
from datetime import date

from flask import Flask, Response, flash, redirect, render_template, request, url_for

from analytics import (
    GRUPOS_MUSCULARES_PADRAO,
    progresso_por_exercicio,
    resumo_geral,
    volume_por_musculo,
)
from database import (
    atualizar_registro,
    buscar_registro,
    cadastrar_exercicio,
    excluir_registro,
    exportar_backup_json,
    importar_backup_json,
    inicializar_banco,
    listar_exercicios,
    listar_registros,
    registrar_serie,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-local-treino-alterar-em-producao")

inicializar_banco()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            exercicio_id = int(request.form.get("exercicio_id", "0"))
            serie = int(request.form.get("serie", "1"))
            repeticoes = int(request.form.get("repeticoes", "0"))
            data_treino = request.form.get("data_treino") or date.today().isoformat()
            observacao = request.form.get("observacao", "")

            if exercicio_id <= 0 or serie <= 0 or repeticoes <= 0:
                flash("Preencha exercício, série e repetições com valores maiores que zero.")
                return redirect(url_for("index"))

            registrar_serie(
                exercicio_id=exercicio_id,
                serie=serie,
                repeticoes=repeticoes,
                data_treino=data_treino,
                observacao=observacao,
            )
            flash("Série registrada com sucesso.")
            return redirect(url_for("index"))
        except ValueError:
            flash("Valores inválidos nos campos numéricos.")
            return redirect(url_for("index"))

    exercicios = listar_exercicios()
    registros_recentes = listar_registros(limite=15)
    resumo_7d = resumo_geral(dias=7)
    return render_template(
        "index.html",
        exercicios=exercicios,
        registros_recentes=registros_recentes,
        resumo_7d=resumo_7d,
        hoje=date.today().isoformat(),
    )


@app.route("/historico", methods=["GET", "POST"])
def historico():
    if request.method == "POST" and "arquivo_backup" in request.files:
        arquivo = request.files["arquivo_backup"]
        if arquivo and arquivo.filename:
            try:
                conteudo = arquivo.read().decode("utf-8")
                inseridos = importar_backup_json(conteudo)
                flash(f"Backup restaurado: {inseridos} registros importados.")
            except Exception as exc:
                flash(f"Erro ao importar backup: {exc}")
        return redirect(url_for("historico"))

    registros = listar_registros(limite=300)
    progressao = progresso_por_exercicio()
    return render_template(
        "historico.html",
        registros=registros,
        progressao=progressao,
    )


@app.route("/backup/exportar")
def exportar_backup():
    conteudo_json = exportar_backup_json()
    nome_arquivo = f"backup_treino_{date.today().isoformat()}.json"
    return Response(
        conteudo_json,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


@app.route("/musculos")
def musculos():
    dias_param = request.args.get("dias", "7")
    try:
        dias = int(dias_param)
        if dias not in (7, 14, 30):
            dias = 7
    except ValueError:
        dias = 7

    resumo = resumo_geral(dias=dias)
    volumes = volume_por_musculo(dias=dias)
    return render_template(
        "musculos.html",
        dias=dias,
        resumo=resumo,
        volumes=volumes,
    )


@app.route("/registro/<int:registro_id>/editar", methods=["GET", "POST"])
def editar_registro(registro_id: int):
    registro = buscar_registro(registro_id)
    if not registro:
        flash("Registro não encontrado.")
        return redirect(url_for("historico"))

    if request.method == "POST":
        try:
            exercicio_id = int(request.form.get("exercicio_id", "0"))
            serie = int(request.form.get("serie", "1"))
            repeticoes = int(request.form.get("repeticoes", "0"))
            data_treino = request.form.get("data_treino") or registro["data_treino"]
            observacao = request.form.get("observacao", "")

            if exercicio_id <= 0 or serie <= 0 or repeticoes <= 0:
                flash("Preencha exercício, série e repetições com valores maiores que zero.")
                return redirect(url_for("editar_registro", registro_id=registro_id))

            atualizar_registro(
                registro_id=registro_id,
                exercicio_id=exercicio_id,
                serie=serie,
                repeticoes=repeticoes,
                data_treino=data_treino,
                observacao=observacao,
            )
            flash("Registro atualizado com sucesso.")
            return redirect(url_for("historico"))
        except ValueError:
            flash("Valores inválidos nos campos numéricos.")

    return render_template(
        "editar_registro.html",
        registro=registro,
        exercicios=listar_exercicios(),
    )


@app.route("/registro/<int:registro_id>/excluir", methods=["POST"])
def remover_registro(registro_id: int):
    excluir_registro(registro_id)
    flash("Registro excluído.")
    return redirect(url_for("historico"))


@app.route("/exercicios/novo", methods=["GET", "POST"])
def novo_exercicio():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        equipamento = request.form.get("equipamento", "colchonete").strip()

        if not nome:
            flash("Informe o nome do exercício.")
            return redirect(url_for("novo_exercicio"))

        musculos_pesos = {}
        for grupo in GRUPOS_MUSCULARES_PADRAO:
            valor_str = request.form.get(f"peso_{grupo}", "0").replace(",", ".").strip()
            try:
                peso = float(valor_str) if valor_str else 0.0
            except ValueError:
                peso = 0.0
            if peso > 0:
                musculos_pesos[grupo] = peso

        if not musculos_pesos:
            flash("Defina um peso maior que zero para pelo menos um grupo muscular.")
            return redirect(url_for("novo_exercicio"))

        cadastrar_exercicio(
            nome=nome,
            equipamento=equipamento,
            musculos_pesos=musculos_pesos,
        )
        flash(f"Exercício '{nome}' salvo com sucesso.")
        return redirect(url_for("index"))

    return render_template(
        "novo_exercicio.html",
        grupos_musculares=GRUPOS_MUSCULARES_PADRAO,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)