import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from flask import flash, redirect, render_template, request, url_for, send_file
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.data import data_bp
from app.models import Marketplace, Sale, User


MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def parse_template_csv(raw_bytes: bytes) -> tuple[list[dict], list[str]]:
    """
    Parse CSV baseado no template padronizado.
    Lê colunas por POSIÇÃO, não por nome.

    Returns:
        Tuple (lista de dicts normalizados, lista de erros)
    """
    errors = []
    parsed_data = []

    # Tentar decodificar com UTF-8
    try:
        text_content = raw_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text_content = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = raw_bytes.decode('latin-1')
            except UnicodeDecodeError:
                errors.append("Erro: Não foi possível decodificar o arquivo. Use UTF-8.")
                return [], errors

    # Ler CSV
    text_stream = io.StringIO(text_content)
    reader = csv.reader(text_stream, delimiter=',')

    # IGNORAR primeira linha (cabeçalho)
    try:
        next(reader)
    except StopIteration:
        errors.append("Arquivo vazio")
        return [], errors

    # Processar linhas por POSIÇÃO
    for line_num, row in enumerate(reader, start=2):  # Linha 2 = primeira com dados
        try:
            # Verificar se tem colunas mínimas
            if len(row) < 5:
                errors.append(f"Linha {line_num}: Dados insuficientes (mínimo 5 colunas)")
                continue

            # LER POR POSIÇÃO (não por nome!)
            normalized = {}

            # Coluna 0: data_venda (obrigatória)
            try:
                date_str = row[0].strip()
                normalized['data_venda'] = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, IndexError):
                errors.append(f"Linha {line_num}: Data inválida (use formato YYYY-MM-DD)")
                continue

            # Coluna 1: sku (obrigatório)
            normalized['sku'] = row[1].strip() if len(row) > 1 and row[1].strip() else None
            if not normalized['sku']:
                errors.append(f"Linha {line_num}: SKU obrigatório")
                continue

            # Coluna 2: nome_produto (obrigatório)
            normalized['nome_produto'] = row[2].strip() if len(row) > 2 and row[2].strip() else None
            if not normalized['nome_produto']:
                errors.append(f"Linha {line_num}: Nome do produto obrigatório")
                continue

            # Coluna 3: status_pedido (obrigatório)
            status = row[3].strip().lower() if len(row) > 3 and row[3].strip() else 'pago'
            valid_statuses = ['pago', 'enviado', 'entregue', 'cancelado']
            normalized['status_pedido'] = status if status in valid_statuses else 'pago'

            # Coluna 4: valor_total_venda (obrigatório)
            try:
                normalized['valor_total_venda'] = Decimal(row[4].strip()) if len(row) > 4 and row[4].strip() else None
                if normalized['valor_total_venda'] is None:
                    errors.append(f"Linha {line_num}: Valor total obrigatório")
                    continue
            except (ValueError, InvalidOperation):
                errors.append(f"Linha {line_num}: Valor total inválido")
                continue

            # Colunas opcionais (5 em diante)
            normalized['numero_pedido'] = row[5].strip() if len(row) > 5 and row[5].strip() else None

            # Coluna 6: unidades
            try:
                normalized['unidades'] = int(row[6].strip()) if len(row) > 6 and row[6].strip() else None
            except (ValueError, IndexError):
                normalized['unidades'] = None

            # Coluna 7: preco_unitario
            try:
                normalized['preco_unitario'] = Decimal(row[7].strip()) if len(row) > 7 and row[7].strip() else None
            except (ValueError, InvalidOperation, IndexError):
                normalized['preco_unitario'] = None

            # Colunas 8-12: dados do cliente e geografia
            normalized['comprador'] = row[8].strip() if len(row) > 8 and row[8].strip() else None
            normalized['cpf_comprador'] = row[9].strip() if len(row) > 9 and row[9].strip() else None
            normalized['estado_comprador'] = row[10].strip() if len(row) > 10 and row[10].strip() else None
            normalized['cidade_comprador'] = row[11].strip() if len(row) > 11 and row[11].strip() else None
            normalized['forma_entrega'] = row[12].strip() if len(row) > 12 and row[12].strip() else None

            # Colunas 13-18: dados financeiros
            for idx, field in [
                (13, 'receita_produtos'),
                (14, 'taxa_parcelamento'),
                (15, 'tarifa_venda_impostos'),
                (16, 'custo_envio'),
                (17, 'lucro_liquido'),
                (18, 'margem_percentual')
            ]:
                try:
                    normalized[field] = Decimal(row[idx].strip()) if len(row) > idx and row[idx].strip() else None
                except (ValueError, InvalidOperation, IndexError):
                    normalized[field] = None

            # Calcular faixa de preço
            preco = normalized.get('preco_unitario') or normalized.get('valor_total_venda')
            if preco:
                if preco < Decimal('50'):
                    normalized['faixa_preco'] = 'Baixo'
                elif preco <= Decimal('200'):
                    normalized['faixa_preco'] = 'Médio'
                else:
                    normalized['faixa_preco'] = 'Alto'

            parsed_data.append(normalized)

        except Exception as e:
            errors.append(f"Linha {line_num}: Erro inesperado - {str(e)}")
            continue

    return parsed_data, errors


@data_bp.route("/upload", methods=["GET"])
@login_required
def upload_form():
    if not current_user.is_manager():
        flash("Acesso restrito aos gestores.", "error")
        return redirect(url_for("dashboard.user_dashboard"))

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    selected_company = request.args.get("company_id", type=int)

    return render_template(
        "data_upload.html",
        marketplaces=marketplaces,
        companies=companies,
        selected_company=selected_company,
    )


@data_bp.route("/download-template")
@login_required
def download_template():
    """Download do template CSV padronizado"""
    import os
    from flask import current_app

    template_path = os.path.join(
        current_app.root_path,
        'static',
        'templates',
        'template_importacao.csv'
    )

    return send_file(
        template_path,
        as_attachment=True,
        download_name='template_importacao_alyal.csv',
        mimetype='text/csv'
    )


@data_bp.route("/upload", methods=["POST"])
@login_required
def upload_submit():
    if not current_user.is_manager():
        flash("Acesso restrito aos gestores.", "error")
        return redirect(url_for("dashboard.user_dashboard"))

    marketplace_id = request.form.get("marketplace_id")
    company_id = request.form.get("company_id")
    file = request.files.get("file")

    # Validações básicas
    try:
        marketplace_id_int = int(marketplace_id)
    except (TypeError, ValueError):
        flash("Selecione um marketplace válido.", "error")
        return redirect(url_for("data.upload_form"))

    try:
        company_id_int = int(company_id) if company_id else None
    except (TypeError, ValueError):
        flash("Selecione uma empresa válida.", "error")
        return redirect(url_for("data.upload_form"))

    marketplace = db.session.get(Marketplace, marketplace_id_int)
    if not marketplace:
        flash("Marketplace não encontrado.", "error")
        return redirect(url_for("data.upload_form"))

    if not file or file.filename == "":
        flash("Envie um arquivo CSV no formato do template.", "error")
        return redirect(url_for("data.upload_form"))

    # Validar extensão
    if not file.filename.lower().endswith('.csv'):
        flash("Apenas arquivos CSV são aceitos. Use o template fornecido.", "error")
        return redirect(url_for("data.upload_form"))

    # Validar tamanho
    file.stream.seek(0, io.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)

    if size > MAX_UPLOAD_SIZE:
        flash("Arquivo excede o tamanho máximo de 50MB.", "error")
        return redirect(url_for("data.upload_form"))

    # Ler arquivo
    raw_bytes = file.read()
    if not raw_bytes:
        flash("Arquivo vazio.", "error")
        return redirect(url_for("data.upload_form"))

    # PROCESSAR com função simples por posição
    parsed_data, errors = parse_template_csv(raw_bytes)

    if not parsed_data:
        flash("Nenhum dado válido encontrado no arquivo.", "error")
        if errors:
            for error in errors[:5]:
                flash(error, "error")
        return redirect(url_for("data.upload_form"))

    # Criar objetos Sale
    sales_to_insert = []
    for row_data in parsed_data:
        try:
            sale = Sale(
                marketplace_id=marketplace.id,
                company_id=company_id_int,
                **row_data
            )
            sales_to_insert.append(sale)
        except Exception as e:
            errors.append(f"Erro ao criar venda: {str(e)}")

    # Salvar no banco
    if sales_to_insert:
        db.session.bulk_save_objects(sales_to_insert)
        db.session.commit()

    # Feedback
    total_rows = len(parsed_data)
    imported_count = len(sales_to_insert)

    flash(
        f"✅ Importação concluída: {imported_count} registros importados de {total_rows} linhas processadas.",
        "success"
    )

    if errors:
        for error in errors[:5]:
            flash(error, "error")
        if len(errors) > 5:
            flash(f"⚠️ {len(errors) - 5} erros adicionais foram omitidos.", "error")

    return redirect(url_for("data.upload_form", company_id=company_id_int))


@data_bp.route("/list")
@login_required
def sales_list():
    if not current_user.is_manager():
        flash("Acesso restrito aos gestores.", "error")
        return redirect(url_for("dashboard.user_dashboard"))

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    page = request.args.get("page", default=1, type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    marketplace_id = request.args.get("marketplace_id", type=int)
    company_id = request.args.get("company_id", type=int)

    query = (
        Sale.query.options(joinedload(Sale.marketplace), joinedload(Sale.company))
        .order_by(Sale.data_venda.desc(), Sale.id.desc())
    )

    try:
        if start_date:
            query = query.filter(Sale.data_venda >= datetime.strptime(start_date, "%Y-%m-%d").date())
        if end_date:
            query = query.filter(Sale.data_venda <= datetime.strptime(end_date, "%Y-%m-%d").date())
    except ValueError:
        flash("Datas inválidas informadas.", "error")
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if marketplace_id:
            params["marketplace_id"] = marketplace_id
        if company_id:
            params["company_id"] = company_id
        return redirect(url_for("data.sales_list", **params))

    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
    if company_id:
        query = query.filter(Sale.company_id == company_id)

    pagination = query.paginate(page=page, per_page=25, error_out=False)

    return render_template(
        "data_list.html",
        marketplaces=marketplaces,
        companies=companies,
        sales=pagination.items,
        pagination=pagination,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        start_date=start_date,
        end_date=end_date,
    )
