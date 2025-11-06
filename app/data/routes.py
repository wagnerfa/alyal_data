import csv
import io
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.data import data_bp
from app.models import Marketplace, Sale


REQUIRED_COLUMNS = {'nome_produto', 'sku', 'status_pedido', 'data_venda', 'valor_total_venda'}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB


def _normalize_status(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value or '')
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.strip().lower().replace(' ', '_').replace('-', '_')


def _parse_date(value: str):
    if not value:
        raise ValueError('data_venda vazia')
    value = value.strip()
    formats = (
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%Y/%m/%d',
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Formato de data inválido: {value}')


def _parse_decimal(value: str) -> Decimal:
    if value is None:
        raise InvalidOperation('valor_total_venda ausente')
    cleaned = value.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
    if not cleaned:
        raise InvalidOperation('valor_total_venda vazio')
    return Decimal(cleaned)


def _ensure_manager_access():
    if not current_user.is_manager():
        flash('Acesso restrito aos gestores.', 'error')
        return redirect(url_for('dashboard.user_dashboard'))
    return None


@data_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    redirect_response = _ensure_manager_access()
    if redirect_response:
        return redirect_response

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    if request.method == 'POST':
        marketplace_id = request.form.get('marketplace_id')
        file = request.files.get('file')

        if not marketplace_id or not marketplace_id.isdigit():
            flash('Selecione um marketplace válido.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        marketplace = Marketplace.query.get(int(marketplace_id))
        if not marketplace:
            flash('Marketplace selecionado não encontrado.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        if not file or file.filename == '':
            flash('Envie um arquivo CSV válido.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        if not file.filename.lower().endswith('.csv'):
            flash('O arquivo deve estar no formato .csv.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        file.stream.seek(0, io.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > MAX_UPLOAD_SIZE:
            flash('O arquivo excede o tamanho máximo permitido de 2MB.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        file.stream.seek(0)
        raw_bytes = file.stream.read()
        try:
            decoded = raw_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = raw_bytes.decode('latin1')

        reader = csv.DictReader(io.StringIO(decoded))
        if not REQUIRED_COLUMNS.issubset({(col or '').strip().lower() for col in reader.fieldnames or []}):
            flash('CSV inválido. Certifique-se de incluir as colunas: nome_produto, sku, status_pedido, data_venda, valor_total_venda.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        sales_to_insert = []
        errors = []

        for line_number, row in enumerate(reader, start=2):
            try:
                normalized_row = {key.strip().lower(): (value or '').strip() for key, value in row.items()}
                if not REQUIRED_COLUMNS.issubset(set(normalized_row.keys())):
                    raise ValueError('Colunas obrigatórias ausentes na linha')

                status = _normalize_status(normalized_row['status_pedido'])
                data_venda = _parse_date(normalized_row['data_venda'])
                valor = _parse_decimal(normalized_row['valor_total_venda'])
                nome_produto = normalized_row['nome_produto']
                sku = normalized_row['sku']

                if not nome_produto or not sku:
                    raise ValueError('Campos nome_produto e sku são obrigatórios')

                sales_to_insert.append(
                    Sale(
                        marketplace_id=marketplace.id,
                        nome_produto=nome_produto,
                        sku=sku,
                        status_pedido=status,
                        data_venda=data_venda,
                        valor_total_venda=valor,
                    )
                )
            except (ValueError, InvalidOperation) as exc:
                errors.append(f'Linha {line_number}: {exc}')

        if errors:
            for error in errors[:5]:
                flash(error, 'error')
            if len(errors) > 5:
                flash(f'{len(errors) - 5} erros adicionais foram omitidos.', 'error')
            return render_template('data_upload.html', marketplaces=marketplaces)

        if sales_to_insert:
            db.session.bulk_save_objects(sales_to_insert)
            db.session.commit()
            flash(f'{len(sales_to_insert)} vendas importadas para {marketplace.nome}.', 'success')
        else:
            flash('Nenhuma venda válida encontrada no arquivo.', 'warning')

        return redirect(url_for('data.upload'))

    return render_template('data_upload.html', marketplaces=marketplaces)


@data_bp.route('/list')
@login_required
def sales_list():
    redirect_response = _ensure_manager_access()
    if redirect_response:
        return redirect_response

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    page = request.args.get('page', default=1, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    marketplace_id = request.args.get('marketplace_id', type=int)

    query = Sale.query.options(joinedload(Sale.marketplace)).order_by(Sale.data_venda.desc(), Sale.id.desc())

    try:
        if start_date:
            query = query.filter(Sale.data_venda >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(Sale.data_venda <= datetime.strptime(end_date, '%Y-%m-%d').date())
    except ValueError:
        flash('Datas inválidas informadas.', 'error')
        return redirect(url_for('data.sales_list'))

    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)

    pagination = query.paginate(page=page, per_page=25, error_out=False)

    return render_template(
        'data_list.html',
        marketplaces=marketplaces,
        sales=pagination.items,
        pagination=pagination,
        selected_marketplace=marketplace_id,
        start_date=start_date,
        end_date=end_date,
    )
