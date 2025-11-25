import os
from datetime import date, datetime, timedelta
from uuid import uuid4

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.dashboard import dashboard_bp
from app.models import ManagerNote, Marketplace, User
from app.services.metrics import (
    abc_by_revenue,
    calculate_rfm_analysis,
    cohort_analysis,
    get_data_boundaries,
    get_kpis,
    monthly_growth_analysis,
    monthly_revenue_totals,
    monthly_sales_counts,
    pareto_analysis,
    products_by_price_range,
    sales_by_city,
    sales_by_day_of_week,
    sales_by_hour_of_day,
    sales_by_shipping_method,
    sales_by_state,
    sales_timeseries,
    sales_with_moving_average,
    shipping_performance,
    status_breakdown,
    top_products_by_revenue,
    top_products_with_margin,
)
from app.utils.formatting import format_currency_br, format_decimal_br
from werkzeug.utils import secure_filename


def _redirect_to_role_dashboard():
    if current_user.is_authenticated and current_user.is_manager():
        return redirect(url_for('dashboard.manager_dashboard'))
    return redirect(url_for('dashboard.user_dashboard'))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _get_filters_from_request():
    source = request.values if request.method == 'POST' else request.args
    start_raw = source.get('start_date')
    end_raw = source.get('end_date')
    marketplace_id = source.get('marketplace_id', type=int)
    company_id = source.get('company_id', type=int)

    end_date = _parse_date(end_raw) or date.today()
    start_date = _parse_date(start_raw) or (end_date - timedelta(days=30))

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    marketplace_id = marketplace_id if marketplace_id and marketplace_id > 0 else None
    company_id = company_id if company_id and company_id > 0 else None
    return start_date, end_date, marketplace_id, company_id


def _get_previous_period(start_date, end_date):
    delta = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=delta - 1)
    return previous_start, previous_end


def _build_redirect_params(start_date, end_date, marketplace_id, company_id=None):
    params = {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    }
    if marketplace_id:
        params['marketplace_id'] = marketplace_id
    if company_id:
        params['company_id'] = company_id
    return params


def _variation_text(current_value, previous_value):
    if previous_value:
        variation = ((current_value - previous_value) / previous_value) * 100
        if variation > 0:
            return (
                f"aumento de {format_decimal_br(variation, 1)}% em relação ao período anterior"
            )
        if variation < 0:
            return (
                f"queda de {format_decimal_br(abs(variation), 1)}% em relação ao período anterior"
            )
        return 'estabilidade em relação ao período anterior'
    if current_value > 0:
        return 'crescimento sobre um período sem registros'
    return 'sem variação em relação ao período anterior'


def _generate_insights(kpis, previous_kpis, abc_data):
    insights = []
    insights.append(
        f"Faturamento do período: {format_currency_br(kpis['faturamento'])} ("
        f"{_variation_text(kpis['faturamento'], previous_kpis['faturamento'])})."
    )
    insights.append(
        "Total de pedidos válidos: "
        f"{format_decimal_br(kpis['pedidos_totais'], 0)} ("
        f"{_variation_text(kpis['pedidos_totais'], previous_kpis['pedidos_totais'])})."
    )
    if kpis['taxa_cancelamento'] > 0:
        insights.append(
            f"Taxa de cancelamento em {format_decimal_br(kpis['taxa_cancelamento'], 1)}% no período analisado."
        )
    else:
        insights.append('Nenhum pedido cancelado no período selecionado.')
    if abc_data:
        top = abc_data[0]
        insights.append(
            "SKU de maior faturamento: "
            f"{top['sku']} com {format_decimal_br(top['percentual'], 1)}% do total (classe {top['classe']})."
        )
    return insights


def _allowed_logo(filename):
    if not filename or '.' not in filename:
        return False
    allowed = current_app.config.get('ALLOWED_LOGO_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in allowed


def _remove_logo_file(filename):
    if not filename:
        return
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder:
        return
    filepath = os.path.join(upload_folder, filename)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        pass


def _save_logo_file(storage, previous=None):
    if not storage or not storage.filename:
        return previous
    filename = secure_filename(storage.filename)
    if not _allowed_logo(filename):
        return previous
    extension = filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid4().hex}.{extension}"
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, unique_name)
    storage.stream.seek(0)
    storage.save(filepath)
    if previous and previous != unique_name:
        _remove_logo_file(previous)
    return unique_name


@dashboard_bp.route('/')
@login_required
def dashboard_index():
    return _redirect_to_role_dashboard()


@dashboard_bp.route('/companies', methods=['GET', 'POST'])
@login_required
def manage_companies():
    if not current_user.is_manager():
        return _redirect_to_role_dashboard()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            username = (request.form.get('username') or '').strip()
            email = (request.form.get('email') or '').strip()
            password = request.form.get('password') or ''
            confirm_password = request.form.get('confirm_password') or ''
            pending_logo = request.files.get('logo')

            errors = []
            if not username or not email or not password:
                errors.append('Informe nome de usuário, e-mail e senha para cadastrar a empresa.')
            if password and len(password) < 6:
                errors.append('A senha deve conter ao menos 6 caracteres.')
            if password != confirm_password:
                errors.append('A confirmação da senha não confere.')
            if username and User.query.filter_by(username=username).first():
                errors.append('Já existe uma empresa com esse nome de usuário.')
            if email and User.query.filter_by(email=email).first():
                errors.append('Já existe uma empresa utilizando esse e-mail.')
            if pending_logo and pending_logo.filename and not _allowed_logo(pending_logo.filename):
                errors.append('Formato de logotipo inválido. Utilize PNG, JPG, JPEG, GIF ou WEBP.')

            if errors:
                for message in errors:
                    flash(message, 'error')
            else:
                logo_filename = None
                if pending_logo and pending_logo.filename:
                    logo_filename = _save_logo_file(pending_logo)
                new_user = User(
                    username=username,
                    email=email,
                    role='user',
                    logo_filename=logo_filename,
                )
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                flash('Empresa cadastrada com sucesso.', 'success')

        elif action == 'password':
            user_id = request.form.get('user_id', type=int)
            new_password = request.form.get('new_password') or ''
            confirm_password = request.form.get('confirm_password') or ''
            company = User.query.filter_by(id=user_id, role='user').first()

            if not company:
                flash('Empresa não encontrada.', 'error')
            else:
                errors = []
                if not new_password:
                    errors.append('Informe a nova senha.')
                if new_password and len(new_password) < 6:
                    errors.append('A nova senha deve conter ao menos 6 caracteres.')
                if new_password != confirm_password:
                    errors.append('A confirmação da senha não confere.')

                if errors:
                    for message in errors:
                        flash(message, 'error')
                else:
                    company.set_password(new_password)
                    db.session.commit()
                    flash('Senha atualizada com sucesso.', 'success')

        elif action == 'logo':
            user_id = request.form.get('user_id', type=int)
            company = User.query.filter_by(id=user_id, role='user').first()
            logo_file = request.files.get('logo')

            if not company:
                flash('Empresa não encontrada.', 'error')
            elif not logo_file or not logo_file.filename:
                flash('Selecione um arquivo de logotipo para enviar.', 'error')
            elif not _allowed_logo(logo_file.filename):
                flash('Formato de logotipo inválido. Utilize PNG, JPG, JPEG, GIF ou WEBP.', 'error')
            else:
                company.logo_filename = _save_logo_file(logo_file, previous=company.logo_filename)
                db.session.commit()
                flash('Logotipo atualizado com sucesso.', 'success')

        elif action == 'delete':
            user_id = request.form.get('user_id', type=int)
            company = User.query.filter_by(id=user_id, role='user').first()
            if not company:
                flash('Empresa não encontrada.', 'error')
            else:
                _remove_logo_file(company.logo_filename)
                db.session.delete(company)
                db.session.commit()
                flash('Empresa removida com sucesso.', 'success')

        return redirect(url_for('dashboard.manage_companies'))

    companies = (
        User.query.filter_by(role='user')
        .order_by(User.username.asc())
        .all()
    )

    allowed_extensions = ', '.join(sorted(current_app.config.get('ALLOWED_LOGO_EXTENSIONS', [])))

    return render_template(
        'dashboard_companies.html',
        companies=companies,
        allowed_extensions=allowed_extensions,
    )


@dashboard_bp.route('/manager', methods=['GET', 'POST'])
@login_required
def manager_dashboard():
    if not current_user.is_manager():
        return _redirect_to_role_dashboard()

    start_date, end_date, marketplace_id, company_id = _get_filters_from_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
    company_ids = [company.id for company in companies]

    if company_id not in company_ids and company_ids:
        company_id = company_ids[0]

    if request.method == 'POST' and 'manager_note' in request.form:
        note_content = request.form.get('manager_note', '').strip()
        company_id_form = request.form.get('company_id', type=int)
        if company_id_form not in company_ids:
            flash('Selecione uma empresa válida antes de salvar.', 'error')
            return redirect(
                url_for(
                    'dashboard.manager_dashboard',
                    **_build_redirect_params(start_date, end_date, marketplace_id, company_id),
                )
            )

        company_id = company_id_form

        if note_content:
            note = ManagerNote.query.filter_by(
                author_id=current_user.id,
                periodo_inicio=start_date,
                periodo_fim=end_date,
                company_id=company_id,
            ).first()
            if note:
                note.conteudo = note_content
            else:
                note = ManagerNote(
                    periodo_inicio=start_date,
                    periodo_fim=end_date,
                    conteudo=note_content,
                    author_id=current_user.id,
                    company_id=company_id,
                )
                db.session.add(note)
            db.session.commit()
            flash('Comentário salvo com sucesso.', 'success')
        else:
            flash('Escreva um comentário antes de salvar.', 'error')

        return redirect(
            url_for(
                'dashboard.manager_dashboard',
                **_build_redirect_params(start_date, end_date, marketplace_id, company_id),
            )
        )

    kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
    timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id, company_id)

    no_data = (not timeseries['values']) and kpis['faturamento'] == 0.0 and kpis['pedidos_totais'] == 0.0
    if no_data:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            if min_date != start_date or max_date != end_date:
                start_date, end_date = min_date, max_date
                kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
                timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id, company_id)

    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_kpis = get_kpis(db.session, previous_start, previous_end, marketplace_id, company_id)
    abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id, company_id)

    manager_note = ManagerNote.query.filter_by(
        author_id=current_user.id,
        periodo_inicio=start_date,
        periodo_fim=end_date,
        company_id=company_id,
    ).first()

    insights = _generate_insights(kpis, previous_kpis, abc_data)

    return render_template(
        'dashboard_manager.html',
        user=current_user,
        marketplaces=marketplaces,
        companies=companies,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        kpis=kpis,
        previous_period=(previous_start, previous_end),
        timeseries_labels=timeseries['labels'],
        timeseries_values=timeseries['values'],
        abc_data=abc_data[:10],
        manager_note=manager_note,
        insights=insights,
    )


@dashboard_bp.route('/user')
@login_required
def user_dashboard():
    if current_user.is_manager():
        return _redirect_to_role_dashboard()

    start_date, end_date, marketplace_id, _ = _get_filters_from_request()
    company_id = current_user.id
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()
    company_id = current_user.id

    kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
    timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id, company_id)

    no_data = (not timeseries['values']) and kpis['faturamento'] == 0.0 and kpis['pedidos_totais'] == 0.0
    if no_data:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            if min_date != start_date or max_date != end_date:
                start_date, end_date = min_date, max_date
                kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
                timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id, company_id)

    status_data = status_breakdown(db.session, start_date, end_date, marketplace_id, company_id)
    status_items = [
        {
            'label': label.replace('_', ' ').title(),
            'value': int(value) if float(value).is_integer() else float(value),
        }
        for label, value in zip(status_data['labels'], status_data['values'])
    ]

    top_products = top_products_by_revenue(db.session, start_date, end_date, marketplace_id)
    monthly_sales = monthly_sales_counts(db.session, start_date, end_date, marketplace_id)
    monthly_revenue = monthly_revenue_totals(db.session, start_date, end_date, marketplace_id)
    sales_by_hour = sales_by_hour_of_day(db.session, start_date, end_date, marketplace_id)
    sales_by_day = sales_by_day_of_week(db.session, start_date, end_date, marketplace_id)

    manager_note = (
        ManagerNote.query
        .filter_by(periodo_inicio=start_date, periodo_fim=end_date, company_id=company_id)
        .order_by(ManagerNote.id.desc())
        .first()
    )

    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_kpis = get_kpis(db.session, previous_start, previous_end, marketplace_id, company_id)
    abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id, company_id)
    insights = _generate_insights(kpis, previous_kpis, abc_data)

    return render_template(
        'dashboard_user.html',
        user=current_user,
        marketplaces=marketplaces,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        kpis=kpis,
        timeseries_labels=timeseries['labels'],
        timeseries_values=timeseries['values'],
        manager_note=manager_note,
        insights=insights,
        status_items=status_items,
        status_labels=status_data['labels'],
        status_values=status_data['values'],
        top_products_labels=top_products['labels'],
        top_products_values=top_products['values'],
        monthly_sales_labels=monthly_sales['labels'],
        monthly_sales_values=monthly_sales['values'],
        monthly_revenue_labels=monthly_revenue['labels'],
        monthly_revenue_values=monthly_revenue['values'],
        sales_by_hour_labels=sales_by_hour['labels'],
        sales_by_hour_values=sales_by_hour['values'],
        sales_by_day_labels=sales_by_day['labels'],
        sales_by_day_values=sales_by_day['values'],
    )


@dashboard_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if current_user.is_manager():
        return _redirect_to_role_dashboard()

    if request.method == 'POST':
        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        errors = []
        if not current_password:
            errors.append('Informe a senha atual.')
        elif not current_user.check_password(current_password):
            errors.append('Senha atual incorreta.')

        if not new_password:
            errors.append('Informe a nova senha.')
        elif len(new_password) < 6:
            errors.append('A nova senha deve conter ao menos 6 caracteres.')

        if new_password != confirm_password:
            errors.append('A confirmação da nova senha não confere.')

        if errors:
            for message in errors:
                flash(message, 'error')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Senha atualizada com sucesso.', 'success')
            return redirect(url_for('dashboard.user_settings'))

    return render_template('user_settings.html', user=current_user)


@dashboard_bp.route('/abc')
@login_required
def abc_view():
    start_date, end_date, marketplace_id, company_id = _get_filters_from_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    if current_user.is_manager():
        companies = (
            User.query.filter_by(role='user')
            .order_by(User.username.asc())
            .all()
        )
        company_ids = [company.id for company in companies]
        if company_id not in company_ids and company_ids:
            company_id = company_ids[0]
    else:
        company_id = current_user.id
        companies = []

    abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id, company_id)
    if not abc_data:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            if min_date != start_date or max_date != end_date:
                start_date, end_date = min_date, max_date
                abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id, company_id)

    chart_slice = abc_data[:10]
    chart_labels = [item['sku'] for item in chart_slice]
    chart_revenue = [round(item['faturamento'], 2) for item in chart_slice]
    chart_cumulative = [round(item['percentual_acumulado'], 2) for item in chart_slice]

    return render_template(
        'dashboard_abc.html',
        marketplaces=marketplaces,
        companies=companies,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        abc_data=abc_data,
        chart_labels=chart_labels,
        chart_revenue=chart_revenue,
        chart_cumulative=chart_cumulative,
    )


@dashboard_bp.route('/status')
@login_required
def status_view():
    start_date, end_date, marketplace_id, company_id = _get_filters_from_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    if current_user.is_manager():
        companies = (
            User.query.filter_by(role='user')
            .order_by(User.username.asc())
            .all()
        )
        company_ids = [company.id for company in companies]
        if company_id not in company_ids and company_ids:
            company_id = company_ids[0]
    else:
        company_id = current_user.id
        companies = []

    breakdown = status_breakdown(db.session, start_date, end_date, marketplace_id, company_id)
    total_current = sum(breakdown['values'])
    if total_current == 0:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            if min_date != start_date or max_date != end_date:
                start_date, end_date = min_date, max_date
                breakdown = status_breakdown(db.session, start_date, end_date, marketplace_id, company_id)
            total_current = sum(breakdown['values'])
    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_breakdown = status_breakdown(db.session, previous_start, previous_end, marketplace_id, company_id)

    current_map = dict(zip(breakdown['labels'], breakdown['values']))
    previous_map = dict(zip(previous_breakdown['labels'], previous_breakdown['values']))

    all_statuses = sorted(
        set(current_map.keys()) | set(previous_map.keys()),
        key=lambda status: current_map.get(status, 0),
        reverse=True,
    )

    status_rows = []
    for status in all_statuses:
        current_count = float(current_map.get(status, 0))
        previous_count = float(previous_map.get(status, 0))
        if previous_count:
            variation = ((current_count - previous_count) / previous_count) * 100
        elif current_count > 0:
            variation = None
        else:
            variation = 0
        status_rows.append({
            'status': status,
            'current': int(current_count) if current_count.is_integer() else current_count,
            'previous': int(previous_count) if previous_count.is_integer() else previous_count,
            'variation': variation,
        })

    status_labels = [label.replace('_', ' ').title() for label in breakdown['labels']]
    status_values = breakdown['values']

    return render_template(
        'dashboard_status.html',
        marketplaces=marketplaces,
        companies=companies,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        status_rows=status_rows,
        status_labels=status_labels,
        status_values=status_values,
        previous_period=(previous_start, previous_end),
    )


@dashboard_bp.route('/analytics')
@login_required
def analytics_dashboard():
    start_date, end_date, marketplace_id, company_id = _get_filters_from_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    # For managers, show company selector; for users, use their own company_id
    if current_user.is_manager():
        companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
        company_ids = [company.id for company in companies]
        if company_id not in company_ids and company_ids:
            company_id = company_ids[0]
    else:
        company_id = current_user.id
        companies = []

    # Check for data and adjust period if needed
    kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
    if kpis['faturamento'] == 0.0 and kpis['pedidos_totais'] == 0.0:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            start_date, end_date = min_date, max_date

    # Geographic Analysis
    state_data = sales_by_state(db.session, start_date, end_date, marketplace_id, company_id, limit=10)
    city_data = sales_by_city(db.session, start_date, end_date, marketplace_id, company_id, limit=15)

    # Product & Margin Analysis
    price_range_data = products_by_price_range(db.session, start_date, end_date, marketplace_id, company_id)
    margin_products = top_products_with_margin(db.session, start_date, end_date, marketplace_id, company_id, limit=10)

    # Shipping Performance
    shipping_data = shipping_performance(db.session, start_date, end_date, marketplace_id, company_id)

    # Customer Analysis
    rfm_data = calculate_rfm_analysis(db.session, start_date, end_date, marketplace_id, company_id)
    cohort_data = cohort_analysis(db.session, start_date, end_date, marketplace_id, company_id)

    # RFM Segment Distribution
    rfm_segments = {}
    for customer in rfm_data:
        segment = customer['segment']
        rfm_segments[segment] = rfm_segments.get(segment, 0) + 1

    return render_template(
        'dashboard_analytics.html',
        marketplaces=marketplaces,
        companies=companies if current_user.is_manager() else [],
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        # Geographic
        state_labels=state_data['labels'],
        state_revenues=state_data['revenues'],
        city_labels=city_data['labels'],
        city_revenues=city_data['revenues'],
        # Product & Margin
        price_range_labels=price_range_data['labels'],
        price_range_revenues=price_range_data['revenues'],
        margin_products=margin_products,
        # Shipping
        shipping_data=shipping_data,
        # Customer Analysis
        rfm_data=rfm_data[:50],  # Limit to top 50 for display
        rfm_segments=rfm_segments,
        cohort_labels=cohort_data['cohort_labels'],
        cohort_period_labels=cohort_data['period_labels'],
        cohort_matrix=cohort_data['retention_matrix'],
        cohort_sizes=cohort_data['cohort_sizes'],
    )

@dashboard_bp.route('/consolidated')
@login_required
def consolidated_dashboard():
    """
    Dashboard consolidado com visão geral de 6 análises em grid 2x3.
    """
    start_date, end_date, marketplace_id, company_id = _get_filters_from_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    # Para gestores, mostrar seletor de empresa; para usuários, usar próprio company_id
    if current_user.is_manager():
        companies = User.query.filter_by(role='user').order_by(User.username.asc()).all()
        company_ids = [company.id for company in companies]
        if company_id not in company_ids and company_ids:
            company_id = company_ids[0]
    else:
        company_id = current_user.id
        companies = []

    # Verificar dados e ajustar período se necessário
    kpis = get_kpis(db.session, start_date, end_date, marketplace_id, company_id)
    if kpis['faturamento'] == 0.0 and kpis['pedidos_totais'] == 0.0:
        min_date, max_date = get_data_boundaries(db.session, marketplace_id, company_id)
        if min_date and max_date:
            if min_date > max_date:
                min_date, max_date = max_date, min_date
            start_date, end_date = min_date, max_date

    # Coletar todas as análises
    # 1. Faturamento diário com tendência
    daily_sales = sales_with_moving_average(db.session, start_date, end_date, marketplace_id, company_id)

    # 2. Top 5 produtos (ABC)
    top_5_products = top_products_by_revenue(db.session, start_date, end_date, marketplace_id, company_id, limit=5)

    # 3. Vendas por hora do dia
    hourly_sales = sales_by_hour_of_day(db.session, start_date, end_date, marketplace_id, company_id)

    # 4. Vendas por dia da semana
    weekly_sales = sales_by_day_of_week(db.session, start_date, end_date, marketplace_id, company_id)

    # 5. Top 5 estados
    top_states = sales_by_state(db.session, start_date, end_date, marketplace_id, company_id, limit=5)

    # 6. Faixa de preço
    price_ranges = products_by_price_range(db.session, start_date, end_date, marketplace_id, company_id)

    return render_template(
        'dashboard_consolidated.html',
        marketplaces=marketplaces,
        companies=companies if current_user.is_manager() else [],
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        selected_company=company_id,
        # Dados para os 6 gráficos
        daily_labels=daily_sales['labels'],
        daily_values=daily_sales['values'],
        daily_ma7=daily_sales['ma7'],
        top5_labels=top_5_products['labels'],
        top5_values=top_5_products['values'],
        hourly_labels=hourly_sales['labels'],
        hourly_values=hourly_sales['values'],
        weekly_labels=weekly_sales['labels'],
        weekly_values=weekly_sales['values'],
        states_labels=top_states['labels'],
        states_revenues=top_states['revenues'],
        price_labels=price_ranges['labels'],
        price_revenues=price_ranges['revenues'],
    )
