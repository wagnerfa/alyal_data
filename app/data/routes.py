import csv
import io
import re
import unicodedata
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Optional

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import db
from app.data import data_bp
from app.models import Marketplace, Sale, User


MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB
REQUIRED_COLUMNS = {"nome_produto", "sku", "status_pedido", "data_venda", "valor_total_venda"}

HEADER_SYNONYMS: Dict[str, Iterable[str]] = {
    "nome_produto": {
        "nome_produto",
        "nome",
        "produto",
        "titulo",
        "titulo_produto",
        "item",
        "descricao",
        "descricao_produto",
    },
    "sku": {
        "sku",
        "codigo",
        "codigo_sku",
        "referencia",
        "id_sku",
    },
    "status_pedido": {
        "status_pedido",
        "status",
        "situacao",
        "status_da_venda",
        "situacao_pedido",
    },
    "data_venda": {
        "data_venda",
        "data",
        "data_pedido",
        "data_da_venda",
        "pedido_data",
    },
    "valor_total_venda": {
        "valor_total_venda",
        "valor",
        "total",
        "valor_total",
        "preco_total",
        "preco",
        "montante",
    },
}

STATUS_ALIASES = {
    "concluido": "entregue",
    "concluida": "entregue",
    "finalizado": "entregue",
    "delivered": "entregue",
    "aprovado": "pago",
    "aprovada": "pago",
    "paid": "pago",
    "shipped": "enviado",
    "postado": "enviado",
    "despachado": "enviado",
    "cancelada": "cancelado",
    "canceled": "cancelado",
}

VALID_STATUSES = {"pago", "enviado", "entregue", "cancelado"}


def normalize_header(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def map_header(header: str) -> Optional[str]:
    for internal, synonyms in HEADER_SYNONYMS.items():
        if header == internal or header in synonyms:
            return internal
    return None


def detect_delimiter(sample: str) -> str:
    if not sample:
        return ";"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        return dialect.delimiter
    except csv.Error:
        if ";" in sample:
            return ";"
        return ","


def parse_date(value: str) -> date:
    if not value:
        raise ValueError("data_venda vazia")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {value}")


def parse_decimal_ptbr_en(value: str) -> Decimal:
    if value is None:
        raise InvalidOperation("valor_total_venda ausente")
    cleaned = (
        value.strip()
        .replace("R$", "")
        .replace(" ", "")
        .replace("\u00a0", "")
    )
    if not cleaned:
        raise InvalidOperation("valor_total_venda vazio")
    comma_pos = cleaned.rfind(",")
    dot_pos = cleaned.rfind(".")
    if comma_pos != -1 or dot_pos != -1:
        decimal_sep = "," if comma_pos > dot_pos else "."
        if decimal_sep == ",":
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "").replace(".", "")
    return Decimal(cleaned)


def normalize_status(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = normalized.replace(" ", "_").replace("-", "_")
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip("_")
    if normalized in STATUS_ALIASES:
        return STATUS_ALIASES[normalized]
    if normalized in VALID_STATUSES:
        return normalized
    return normalized


def _ensure_manager_access():
    if not current_user.is_manager():
        flash("Acesso restrito aos gestores.", "error")
        return redirect(url_for("dashboard.user_dashboard"))
    return None


@data_bp.route("/upload", methods=["GET"])
@login_required
def upload_form():
    redirect_response = _ensure_manager_access()
    if redirect_response:
        return redirect_response

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    selected_company = request.args.get("company_id", type=int)
    return render_template(
        "data_upload.html",
        marketplaces=marketplaces,
        companies=companies,
        selected_company=selected_company,
    )


@data_bp.route("/upload", methods=["POST"])
@login_required
def upload_submit():
    redirect_response = _ensure_manager_access()
    if redirect_response:
        return redirect_response

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    marketplace_id = request.form.get("marketplace_id")
    company_id = request.form.get("company_id")
    selected_company_id = None
    file = request.files.get("file")

    try:
        marketplace_id_int = int(marketplace_id)
    except (TypeError, ValueError):
        flash("Selecione um marketplace válido.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_company=selected_company_id,
        )

    try:
        company_id_int = int(company_id) if company_id else None
        selected_company_id = company_id_int
    except (TypeError, ValueError):
        flash("Selecione uma empresa válida.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace_id_int,
            selected_company=selected_company_id,
        )

    if company_id and not company_id_int:
        flash("Selecione uma empresa válida.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace_id_int,
            selected_company=selected_company_id,
        )

    company = None
    if company_id_int:
        company = db.session.get(User, company_id_int)
        if not company or company.role != 'user':
            flash("Selecione uma empresa válida.", "error")
            return render_template(
                "data_upload.html",
                marketplaces=marketplaces,
                companies=companies,
                selected_marketplace=marketplace_id_int,
                selected_company=selected_company_id,
            )
        selected_company_id = company.id

    marketplace = db.session.get(Marketplace, marketplace_id_int)
    if not marketplace:
        flash("Marketplace selecionado não encontrado.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace_id_int,
            selected_company=selected_company_id,
        )

    if not file or file.filename == "":
        flash("Envie um arquivo CSV válido.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    if not file.filename.lower().endswith(".csv"):
        flash("O arquivo deve estar no formato .csv.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    file.stream.seek(0, io.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_UPLOAD_SIZE:
        flash("O arquivo excede o tamanho máximo permitido de 2MB.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    raw_bytes = file.read()
    if not raw_bytes:
        flash("O arquivo enviado está vazio.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    buffer = io.BytesIO(raw_bytes)
    text_stream = io.TextIOWrapper(buffer, encoding="utf-8-sig", newline="")
    sample = text_stream.read(2048)
    delimiter = detect_delimiter(sample)
    text_stream.seek(0)
    reader = csv.DictReader(text_stream, delimiter=delimiter)

    if not reader.fieldnames:
        flash("Não foi possível identificar o cabeçalho do CSV.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    header_map: Dict[str, str] = {}
    for original_header in reader.fieldnames:
        normalized = normalize_header(original_header)
        internal_name = map_header(normalized)
        if internal_name and internal_name not in header_map:
            header_map[internal_name] = original_header

    missing_columns = sorted(REQUIRED_COLUMNS - set(header_map.keys()))
    if missing_columns:
        missing_str = ", ".join(missing_columns)
        flash(f"CSV inválido. Colunas ausentes: {missing_str}.", "error")
        return render_template(
            "data_upload.html",
            marketplaces=marketplaces,
            companies=companies,
            selected_marketplace=marketplace.id,
            selected_company=selected_company_id,
        )

    sales_to_insert = []
    errors = []
    total_rows = 0

    for line_number, row in enumerate(reader, start=2):
        total_rows += 1
        line_data = {key: (row.get(source) or "").strip() for key, source in header_map.items()}

        try:
            nome_produto = line_data["nome_produto"].strip()
            sku = line_data["sku"].strip()
            if not nome_produto:
                raise ValueError("nome_produto vazio")
            if not sku:
                raise ValueError("sku vazio")

            status = normalize_status(line_data["status_pedido"])
            if not status:
                raise ValueError("status_pedido inválido")

            data_venda = parse_date(line_data["data_venda"])
            valor_total = parse_decimal_ptbr_en(line_data["valor_total_venda"])

            sale = Sale(
                marketplace_id=marketplace.id,
                company_id=company.id if company else None,
                nome_produto=nome_produto,
                sku=sku,
                status_pedido=status,
                data_venda=data_venda,
                valor_total_venda=valor_total,
            )
            sales_to_insert.append(sale)
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"Linha {line_number}: {exc}")

    imported_count = len(sales_to_insert)
    ignored_count = total_rows - imported_count

    if sales_to_insert:
        db.session.bulk_save_objects(sales_to_insert)
        db.session.commit()

    summary_message = (
        f"Importação concluída: {total_rows} linhas lidas, "
        f"{imported_count} importadas, {ignored_count} ignoradas."
    )
    flash(summary_message, "success" if imported_count and not errors else "warning")

    if errors:
        for error in errors[:5]:
            flash(error, "error")
        if len(errors) > 5:
            flash(f"{len(errors) - 5} erros adicionais foram omitidos.", "error")

    redirect_params = {}
    if selected_company_id:
        redirect_params["company_id"] = selected_company_id
    return redirect(url_for("data.upload_form", **redirect_params))


@data_bp.route("/list")
@login_required
def sales_list():
    redirect_response = _ensure_manager_access()
    if redirect_response:
        return redirect_response

    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    page = request.args.get("page", default=1, type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    marketplace_id = request.args.get("marketplace_id", type=int)
    company_id = request.args.get("company_id", type=int)

    query = Sale.query.options(joinedload(Sale.marketplace)).order_by(Sale.data_venda.desc(), Sale.id.desc())

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
