from datetime import date, datetime, timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.dashboard import dashboard_bp
from app.models import ManagerNote, Marketplace
from app.services.metrics import (
    abc_by_revenue,
    get_kpis,
    sales_timeseries,
    status_breakdown,
)


def _redirect_to_role_dashboard():
    if current_user.is_authenticated and current_user.is_manager():
        return redirect(url_for('dashboard.manager_dashboard'))
    return redirect(url_for('dashboard.user_dashboard'))


def _parse_date_input(value, fallback):
    if not value:
        return fallback
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return fallback


def _get_filters_from_source(source):
    today = date.today()
    default_end = today
    default_start = today - timedelta(days=29)

    start_date = _parse_date_input(source.get('start_date'), default_start)
    end_date = _parse_date_input(source.get('end_date'), default_end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    marketplace_value = source.get('marketplace_id')
    try:
        marketplace_id = int(marketplace_value) if marketplace_value else None
    except (TypeError, ValueError):
        marketplace_id = None

    return start_date, end_date, marketplace_id


def _get_filters_for_request():
    source = request.values if request.method == 'POST' else request.args
    return _get_filters_from_source(source)


def _get_previous_period(start_date, end_date):
    delta = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=delta - 1)
    return previous_start, previous_end


def _build_redirect_params(start_date, end_date, marketplace_id):
    params = {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    }
    if marketplace_id:
        params['marketplace_id'] = marketplace_id
    return params


def _variation_text(current_value, previous_value):
    if previous_value:
        variation = ((current_value - previous_value) / previous_value) * 100
        if variation > 0:
            return f'aumento de {variation:.1f}% em relação ao período anterior'
        if variation < 0:
            return f'queda de {abs(variation):.1f}% em relação ao período anterior'
        return 'estabilidade em relação ao período anterior'
    if current_value > 0:
        return 'crescimento sobre um período sem registros'
    return 'sem variação em relação ao período anterior'


def _generate_insights(kpis, previous_kpis, abc_data):
    insights = []
    insights.append(
        f"Faturamento do período: R$ {kpis['faturamento']:.2f} ({_variation_text(kpis['faturamento'], previous_kpis['faturamento'])})."
    )
    insights.append(
        f"Total de pedidos válidos: {kpis['pedidos_totais']} ({_variation_text(kpis['pedidos_totais'], previous_kpis['pedidos_totais'])})."
    )
    if kpis['taxa_cancelamento'] > 0:
        insights.append(f"Taxa de cancelamento em {kpis['taxa_cancelamento']:.1f}% no período analisado.")
    else:
        insights.append('Nenhum pedido cancelado no período selecionado.')
    if abc_data:
        top = abc_data[0]
        insights.append(
            f"SKU de maior faturamento: {top['sku']} com {top['percentual']:.1f}% do total (classe {top['classe']})."
        )
    return insights


@dashboard_bp.route('/')
@login_required
def dashboard_index():
    return _redirect_to_role_dashboard()


@dashboard_bp.route('/manager', methods=['GET', 'POST'])
@login_required
def manager_dashboard():
    if not current_user.is_manager():
        return _redirect_to_role_dashboard()

    start_date, end_date, marketplace_id = _get_filters_for_request()
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    if request.method == 'POST' and 'manager_note' in request.form:
        note_content = request.form.get('manager_note', '').strip()
        if note_content:
            note = ManagerNote.query.filter_by(
                author_id=current_user.id,
                periodo_inicio=start_date,
                periodo_fim=end_date,
            ).first()
            if note:
                note.conteudo = note_content
            else:
                note = ManagerNote(
                    periodo_inicio=start_date,
                    periodo_fim=end_date,
                    conteudo=note_content,
                    author_id=current_user.id,
                )
                db.session.add(note)
            db.session.commit()
            flash('Comentário salvo com sucesso.', 'success')
        else:
            flash('Escreva um comentário antes de salvar.', 'error')

        return redirect(url_for('dashboard.manager_dashboard', **_build_redirect_params(start_date, end_date, marketplace_id)))

    kpis = get_kpis(db.session, start_date, end_date, marketplace_id)
    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_kpis = get_kpis(db.session, previous_start, previous_end, marketplace_id)
    timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id)
    abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id)

    timeseries_labels = [point['data'] for point in timeseries]
    timeseries_values = [round(point['faturamento_diario'], 2) for point in timeseries]

    manager_note = ManagerNote.query.filter_by(
        author_id=current_user.id,
        periodo_inicio=start_date,
        periodo_fim=end_date,
    ).first()

    insights = _generate_insights(kpis, previous_kpis, abc_data)

    return render_template(
        'dashboard_manager.html',
        user=current_user,
        marketplaces=marketplaces,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        kpis=kpis,
        previous_period=(previous_start, previous_end),
        timeseries_labels=timeseries_labels,
        timeseries_values=timeseries_values,
        abc_data=abc_data[:10],
        manager_note=manager_note,
        insights=insights,
    )


@dashboard_bp.route('/user')
@login_required
def user_dashboard():
    if current_user.is_manager():
        return _redirect_to_role_dashboard()

    start_date, end_date, marketplace_id = _get_filters_from_source(request.args)
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    kpis = get_kpis(db.session, start_date, end_date, marketplace_id)
    timeseries = sales_timeseries(db.session, start_date, end_date, marketplace_id)
    timeseries_labels = [point['data'] for point in timeseries]
    timeseries_values = [round(point['faturamento_diario'], 2) for point in timeseries]

    manager_note = (
        ManagerNote.query
        .filter_by(periodo_inicio=start_date, periodo_fim=end_date)
        .order_by(ManagerNote.id.desc())
        .first()
    )

    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_kpis = get_kpis(db.session, previous_start, previous_end, marketplace_id)
    insights = _generate_insights(kpis, previous_kpis, abc_by_revenue(db.session, start_date, end_date, marketplace_id))

    return render_template(
        'dashboard_user.html',
        user=current_user,
        marketplaces=marketplaces,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        kpis=kpis,
        timeseries_labels=timeseries_labels,
        timeseries_values=timeseries_values,
        manager_note=manager_note,
        insights=insights,
    )


@dashboard_bp.route('/abc')
@login_required
def abc_view():
    start_date, end_date, marketplace_id = _get_filters_from_source(request.args)
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    abc_data = abc_by_revenue(db.session, start_date, end_date, marketplace_id)
    chart_slice = abc_data[:10]
    chart_labels = [item['sku'] for item in chart_slice]
    chart_revenue = [round(item['faturamento'], 2) for item in chart_slice]
    chart_cumulative = [round(item['percentual_acumulado'], 2) for item in chart_slice]

    return render_template(
        'dashboard_abc.html',
        marketplaces=marketplaces,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        abc_data=abc_data,
        chart_labels=chart_labels,
        chart_revenue=chart_revenue,
        chart_cumulative=chart_cumulative,
    )


@dashboard_bp.route('/status')
@login_required
def status_view():
    start_date, end_date, marketplace_id = _get_filters_from_source(request.args)
    marketplaces = Marketplace.query.order_by(Marketplace.nome.asc()).all()

    breakdown = status_breakdown(db.session, start_date, end_date, marketplace_id)
    previous_start, previous_end = _get_previous_period(start_date, end_date)
    previous_breakdown = status_breakdown(db.session, previous_start, previous_end, marketplace_id)

    all_statuses = sorted(
        set(breakdown.keys()) | set(previous_breakdown.keys()),
        key=lambda status: breakdown.get(status, 0),
        reverse=True,
    )
    status_rows = []
    for status in all_statuses:
        current_count = breakdown.get(status, 0)
        previous_count = previous_breakdown.get(status, 0)
        if previous_count:
            variation = ((current_count - previous_count) / previous_count) * 100
        elif current_count > 0:
            variation = None
        else:
            variation = 0
        status_rows.append({
            'status': status,
            'current': current_count,
            'previous': previous_count,
            'variation': variation,
        })

    status_labels = [row['status'].replace('_', ' ').title() for row in status_rows]
    status_values = [row['current'] for row in status_rows]

    return render_template(
        'dashboard_status.html',
        marketplaces=marketplaces,
        start_date=start_date,
        end_date=end_date,
        selected_marketplace=marketplace_id,
        status_rows=status_rows,
        status_labels=status_labels,
        status_values=status_values,
        previous_period=(previous_start, previous_end),
    )
