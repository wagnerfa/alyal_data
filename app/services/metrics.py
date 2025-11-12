from decimal import Decimal
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, func, extract
from sqlalchemy.orm import Session

from app.models import Sale


VALID_STATUSES = {'pago', 'enviado', 'entregue'}
CANCELLED_STATUS = 'cancelado'
STATUS_ALIASES = {
    'concluido': 'entregue',
    'concluida': 'entregue',
    'concluído': 'entregue',
    'concluída': 'entregue',
    'finalizado': 'entregue',
    'finalizada': 'entregue',
    'delivered': 'entregue',
    'aprovado': 'pago',
    'aprovada': 'pago',
    'paid': 'pago',
    'pago': 'pago',
    'enviado': 'enviado',
    'shipped': 'enviado',
    'postado': 'enviado',
    'despachado': 'enviado',
    'cancelado': 'cancelado',
    'cancelada': 'cancelado',
    'canceled': 'cancelado',
}


def _apply_common_filters(query, start, end, marketplace_id, company_id=None):
    if start:
        query = query.filter(Sale.data_venda >= start)
    if end:
        query = query.filter(Sale.data_venda <= end)
    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
    if company_id:
        query = query.filter(Sale.company_id == company_id)
    return query


def _normalize_status(value: str) -> str:
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', value)
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = normalized.replace(' ', '_').replace('-', '_')
    normalized = re.sub(r'_+', '_', normalized)
    normalized = normalized.strip('_')
    return STATUS_ALIASES.get(normalized, normalized)


def get_kpis(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> Dict[str, float]:
    base_query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        base_query.with_entities(
            Sale.status_pedido,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total')
        )
        .group_by(Sale.status_pedido)
        .all()
    )

    faturamento_decimal = Decimal(0)
    pedidos_totais = 0
    cancelados = 0

    for status_value, count, total in rows:
        normalized = _normalize_status(status_value)
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        if normalized in VALID_STATUSES:
            pedidos_totais += count
            faturamento_decimal += total_decimal
        elif normalized == CANCELLED_STATUS:
            cancelados += count

    total_considerado = pedidos_totais + cancelados
    ticket_medio_decimal = (faturamento_decimal / pedidos_totais) if pedidos_totais else Decimal(0)
    ticket_medio = float(ticket_medio_decimal.quantize(Decimal('0.01')))
    taxa_cancelamento = float(round((cancelados / total_considerado) * 100, 2)) if total_considerado else 0.0

    return {
        'faturamento': float(faturamento_decimal.quantize(Decimal('0.01'))),
        'pedidos_totais': float(pedidos_totais),
        'ticket_medio': ticket_medio,
        'taxa_cancelamento': taxa_cancelamento,
    }


def sales_timeseries(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.data_venda,
            Sale.status_pedido,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total')
        )
        .group_by(Sale.data_venda, Sale.status_pedido)
        .order_by(Sale.data_venda.asc())
        .all()
    )

    aggregated: Dict[str, Decimal] = {}
    for data_venda, status_value, total in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        key = data_venda.isoformat()
        aggregated[key] = aggregated.get(key, Decimal(0)) + total_decimal

    labels = []
    values: List[float] = []
    for date_key in sorted(aggregated.keys()):
        labels.append(date_key)
        total = aggregated[date_key]
        if isinstance(total, Decimal):
            total = total.quantize(Decimal('0.01'))
        values.append(float(total))

    return {
        'labels': labels,
        'values': values,
    }


def status_breakdown(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.status_pedido,
            func.count(Sale.id)
        )
        .group_by(Sale.status_pedido)
        .order_by(func.count(Sale.id).desc())
        .all()
    )

    labels: List[str] = []
    values: List[float] = []
    for status_value, count in rows:
        normalized = _normalize_status(status_value)
        labels.append(normalized)
        values.append(float(count))

    return {
        'labels': labels,
        'values': values,
    }


def abc_by_revenue(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[Dict[str, float]]:
    thresholds = thresholds or {'A': 0.8, 'B': 0.95}

    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.sku,
            func.max(Sale.nome_produto).label('nome_produto'),
            Sale.status_pedido,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total')
        )
        .group_by(Sale.sku, Sale.status_pedido)
        .order_by(desc('total'))
        .all()
    )

    aggregated: Dict[str, Dict[str, Decimal]] = {}
    for sku, nome_produto, status_value, total in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        if sku not in aggregated:
            aggregated[sku] = {
                'nome_produto': nome_produto,
                'total': Decimal(0),
            }
        aggregated[sku]['total'] += total_decimal

    sorted_items = sorted(
        aggregated.items(),
        key=lambda item: item[1]['total'],
        reverse=True,
    )

    total_revenue = sum(data['total'] for _, data in sorted_items)
    total_revenue = total_revenue or Decimal(0)

    acumulado = Decimal(0)
    resultado = []
    for sku, data in sorted_items:
        faturamento_decimal = data['total']
        percentual = (faturamento_decimal / total_revenue * 100) if total_revenue else Decimal(0)
        acumulado += percentual

        classe = 'C'
        acumulado_ratio = float(acumulado / 100)
        if acumulado_ratio <= thresholds.get('A', 0.8):
            classe = 'A'
        elif acumulado_ratio <= thresholds.get('B', 0.95):
            classe = 'B'

        resultado.append({
            'sku': sku,
            'nome_produto': data['nome_produto'],
            'faturamento': float(faturamento_decimal),
            'percentual': float(percentual),
            'percentual_acumulado': float(acumulado),
            'classe': classe,
        })

    return resultado


def get_data_boundaries(
    session: Session,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
):
    query = session.query(func.min(Sale.data_venda), func.max(Sale.data_venda))
    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
    if company_id:
        query = query.filter(Sale.company_id == company_id)
    min_date, max_date = query.first() or (None, None)
    return min_date, max_date


def top_products_by_revenue(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
    limit: int = 5,
) -> Dict[str, List]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.sku,
            func.max(Sale.nome_produto).label('nome_produto'),
            Sale.status_pedido,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total'),
        )
        .group_by(Sale.sku, Sale.status_pedido)
        .all()
    )

    aggregated: Dict[str, Dict[str, Decimal]] = {}
    for sku, nome_produto, status_value, total in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        if sku not in aggregated:
            aggregated[sku] = {
                'nome_produto': nome_produto,
                'total': Decimal(0),
            }
        aggregated[sku]['total'] += total_decimal

    sorted_items = sorted(
        aggregated.items(),
        key=lambda item: item[1]['total'],
        reverse=True,
    )[:limit]

    labels: List[str] = []
    values: List[float] = []
    details: List[Dict[str, str]] = []

    for sku, data in sorted_items:
        nome_produto = data['nome_produto'] or ''
        label = nome_produto.strip() or sku or '—'
        total_decimal = data['total'].quantize(Decimal('0.01'))
        labels.append(label)
        values.append(float(total_decimal))
        details.append(
            {
                'sku': sku,
                'nome_produto': nome_produto,
                'faturamento': float(total_decimal),
            }
        )

    return {
        'labels': labels,
        'values': values,
        'items': details,
    }


def _month_key(value) -> Tuple[int, int]:
    return value.year, value.month


def monthly_sales_counts(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.data_venda,
            Sale.status_pedido,
            func.count(Sale.id),
        )
        .group_by(Sale.data_venda, Sale.status_pedido)
        .order_by(Sale.data_venda.asc())
        .all()
    )

    monthly_totals: Dict[Tuple[int, int], int] = defaultdict(int)
    for data_venda, status_value, count in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        monthly_totals[_month_key(data_venda)] += int(count)

    sorted_keys = sorted(monthly_totals.keys())
    labels: List[str] = []
    values: List[float] = []
    for year, month in sorted_keys:
        labels.append(f"{month:02d}/{year}")
        values.append(float(monthly_totals[(year, month)]))

    return {'labels': labels, 'values': values}


def monthly_revenue_totals(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id, company_id)

    rows = (
        query.with_entities(
            Sale.data_venda,
            Sale.status_pedido,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total'),
        )
        .group_by(Sale.data_venda, Sale.status_pedido)
        .order_by(Sale.data_venda.asc())
        .all()
    )

    monthly_totals: Dict[Tuple[int, int], Decimal] = defaultdict(lambda: Decimal(0))
    for data_venda, status_value, total in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        monthly_totals[_month_key(data_venda)] += total_decimal

    sorted_keys = sorted(monthly_totals.keys())
    labels: List[str] = []
    values: List[float] = []
    for year, month in sorted_keys:
        labels.append(f"{month:02d}/{year}")
        total_decimal = monthly_totals[(year, month)].quantize(Decimal('0.01'))
        values.append(float(total_decimal))

    return {'labels': labels, 'values': values}
# ========================================
# NOVAS MÉTRICAS - Análises Avançadas
# ========================================


# Análises Temporais
# ==================

def sales_by_hour_of_day(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    """
    Retorna vendas agrupadas por hora do dia (0-23).
    Útil para identificar picos de vendas ao longo do dia.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.with_entities(
            extract('hour', Sale.data_venda).label('hour'),
            func.count(Sale.id),
            Sale.status_pedido,
        )
        .group_by('hour', Sale.status_pedido)
        .all()
    )

    hourly_counts: Dict[int, int] = defaultdict(int)
    for hour, count, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        hour_int = int(hour) if hour is not None else 0
        hourly_counts[hour_int] += int(count)

    # Garantir que todas as horas (0-23) estejam presentes
    labels = [f"{h:02d}:00" for h in range(24)]
    values = [float(hourly_counts.get(h, 0)) for h in range(24)]

    return {'labels': labels, 'values': values}


def sales_by_day_of_week(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List[float]]:
    """
    Retorna vendas agrupadas por dia da semana.
    0 = Segunda, 6 = Domingo
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.with_entities(
            extract('dow', Sale.data_venda).label('dow'),  # 0=domingo, 6=sábado
            func.count(Sale.id),
            Sale.status_pedido,
        )
        .group_by('dow', Sale.status_pedido)
        .all()
    )

    daily_counts: Dict[int, int] = defaultdict(int)
    for dow, count, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue
        dow_int = int(dow) if dow is not None else 0
        # Converter de SQL (0=domingo) para Python (0=segunda)
        dow_adjusted = (dow_int + 6) % 7  # Ajuste para segunda=0
        daily_counts[dow_adjusted] += int(count)

    days_pt = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
    values = [float(daily_counts.get(i, 0)) for i in range(7)]

    return {'labels': days_pt, 'values': values}


def monthly_trend_with_growth(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List]:
    """
    Retorna faturamento mensal com percentual de crescimento.
    """
    monthly_data = monthly_revenue_totals(session, start, end, marketplace_id)
    labels = monthly_data['labels']
    values = monthly_data['values']

    growth = []
    for i, value in enumerate(values):
        if i == 0:
            growth.append(0.0)  # Primeiro mês sem comparação
        else:
            prev_value = values[i - 1]
            if prev_value > 0:
                pct_growth = ((value - prev_value) / prev_value) * 100
                growth.append(round(pct_growth, 2))
            else:
                growth.append(0.0)

    return {
        'labels': labels,
        'revenue': values,
        'growth_pct': growth,
    }


# Análises Geográficas
# ====================

def sales_by_state(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    limit: int = 10,
) -> Dict[str, List]:
    """
    Retorna vendas agrupadas por estado (top N).
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.estado_comprador.isnot(None))
        .with_entities(
            Sale.estado_comprador,
            func.count(Sale.id).label('count'),
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('revenue'),
            Sale.status_pedido,
        )
        .group_by(Sale.estado_comprador, Sale.status_pedido)
        .all()
    )

    state_data: Dict[str, Dict] = {}
    for state, count, revenue, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue

        if state not in state_data:
            state_data[state] = {'count': 0, 'revenue': Decimal(0)}

        state_data[state]['count'] += int(count)
        revenue_decimal = revenue if isinstance(revenue, Decimal) else Decimal(revenue or 0)
        state_data[state]['revenue'] += revenue_decimal

    # Ordenar por faturamento
    sorted_states = sorted(
        state_data.items(),
        key=lambda x: x[1]['revenue'],
        reverse=True
    )[:limit]

    labels = [state for state, _ in sorted_states]
    counts = [float(data['count']) for _, data in sorted_states]
    revenues = [float(data['revenue'].quantize(Decimal('0.01'))) for _, data in sorted_states]

    return {
        'labels': labels,
        'counts': counts,
        'revenues': revenues,
    }


def sales_by_city(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    limit: int = 15,
) -> Dict[str, List]:
    """
    Retorna vendas agrupadas por cidade (top N).
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.cidade_comprador.isnot(None))
        .with_entities(
            Sale.cidade_comprador,
            Sale.estado_comprador,
            func.count(Sale.id).label('count'),
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('revenue'),
            Sale.status_pedido,
        )
        .group_by(Sale.cidade_comprador, Sale.estado_comprador, Sale.status_pedido)
        .all()
    )

    city_data: Dict[Tuple[str, str], Dict] = {}
    for city, state, count, revenue, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue

        key = (city, state or '')
        if key not in city_data:
            city_data[key] = {'count': 0, 'revenue': Decimal(0)}

        city_data[key]['count'] += int(count)
        revenue_decimal = revenue if isinstance(revenue, Decimal) else Decimal(revenue or 0)
        city_data[key]['revenue'] += revenue_decimal

    # Ordenar por faturamento
    sorted_cities = sorted(
        city_data.items(),
        key=lambda x: x[1]['revenue'],
        reverse=True
    )[:limit]

    labels = [f"{city} - {state}" if state else city for (city, state), _ in sorted_cities]
    counts = [float(data['count']) for _, data in sorted_cities]
    revenues = [float(data['revenue'].quantize(Decimal('0.01'))) for _, data in sorted_cities]

    return {
        'labels': labels,
        'counts': counts,
        'revenues': revenues,
    }


# Análises de Produtos e Margens
# ===============================

def products_by_price_range(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List]:
    """
    Retorna distribuição de produtos por faixa de preço.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.faixa_preco.isnot(None))
        .with_entities(
            Sale.faixa_preco,
            func.count(Sale.id).label('count'),
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('revenue'),
            Sale.status_pedido,
        )
        .group_by(Sale.faixa_preco, Sale.status_pedido)
        .all()
    )

    range_data: Dict[str, Dict] = {}
    for price_range, count, revenue, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue

        if price_range not in range_data:
            range_data[price_range] = {'count': 0, 'revenue': Decimal(0)}

        range_data[price_range]['count'] += int(count)
        revenue_decimal = revenue if isinstance(revenue, Decimal) else Decimal(revenue or 0)
        range_data[price_range]['revenue'] += revenue_decimal

    # Ordenar por ordem lógica: Baixo, Médio, Alto
    order = {'Baixo': 0, 'Médio': 1, 'Alto': 2}
    sorted_ranges = sorted(
        range_data.items(),
        key=lambda x: order.get(x[0], 999)
    )

    labels = [price_range for price_range, _ in sorted_ranges]
    counts = [float(data['count']) for _, data in sorted_ranges]
    revenues = [float(data['revenue'].quantize(Decimal('0.01'))) for _, data in sorted_ranges]

    return {
        'labels': labels,
        'counts': counts,
        'revenues': revenues,
    }


def top_products_with_margin(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    limit: int = 10,
) -> List[Dict]:
    """
    Retorna produtos com melhor margem de lucro.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.margem_percentual.isnot(None))
        .filter(Sale.lucro_liquido.isnot(None))
        .with_entities(
            Sale.sku,
            func.max(Sale.nome_produto).label('nome_produto'),
            func.avg(Sale.margem_percentual).label('avg_margin'),
            func.sum(Sale.lucro_liquido).label('total_profit'),
            func.count(Sale.id).label('sales_count'),
            Sale.status_pedido,
        )
        .group_by(Sale.sku, Sale.status_pedido)
        .all()
    )

    product_data: Dict[str, Dict] = {}
    for sku, nome, avg_margin, total_profit, sales_count, status_value in rows:
        normalized = _normalize_status(status_value)
        if normalized not in VALID_STATUSES:
            continue

        if sku not in product_data:
            product_data[sku] = {
                'nome_produto': nome,
                'avg_margin': Decimal(0),
                'total_profit': Decimal(0),
                'sales_count': 0,
                'margin_sum': Decimal(0),
                'margin_count': 0,
            }

        margin_decimal = avg_margin if isinstance(avg_margin, Decimal) else Decimal(avg_margin or 0)
        profit_decimal = total_profit if isinstance(total_profit, Decimal) else Decimal(total_profit or 0)

        product_data[sku]['margin_sum'] += margin_decimal * int(sales_count)
        product_data[sku]['margin_count'] += int(sales_count)
        product_data[sku]['total_profit'] += profit_decimal
        product_data[sku]['sales_count'] += int(sales_count)

    # Calcular margem média ponderada
    for sku, data in product_data.items():
        if data['margin_count'] > 0:
            data['avg_margin'] = data['margin_sum'] / data['margin_count']

    # Ordenar por margem média
    sorted_products = sorted(
        product_data.items(),
        key=lambda x: x[1]['avg_margin'],
        reverse=True
    )[:limit]

    result = []
    for sku, data in sorted_products:
        result.append({
            'sku': sku,
            'nome_produto': data['nome_produto'],
            'avg_margin': float(data['avg_margin'].quantize(Decimal('0.01'))),
            'total_profit': float(data['total_profit'].quantize(Decimal('0.01'))),
            'sales_count': data['sales_count'],
        })

    return result


def shipping_performance(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, float]:
    """
    Retorna métricas de desempenho de envio.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .with_entities(
            func.count(Sale.id).label('total_orders'),
            func.avg(Sale.custo_envio).label('avg_shipping_cost'),
            func.avg(Sale.receita_envio).label('avg_shipping_revenue'),
            func.sum(Sale.custo_envio).label('total_shipping_cost'),
            func.sum(Sale.receita_envio).label('total_shipping_revenue'),
        )
        .first()
    )

    if not rows or rows[0] == 0:
        return {
            'total_orders': 0,
            'avg_shipping_cost': 0.0,
            'avg_shipping_revenue': 0.0,
            'total_shipping_cost': 0.0,
            'total_shipping_revenue': 0.0,
            'shipping_margin': 0.0,
        }

    total_orders, avg_cost, avg_revenue, total_cost, total_revenue = rows

    avg_cost_dec = Decimal(avg_cost or 0)
    avg_revenue_dec = Decimal(avg_revenue or 0)
    total_cost_dec = Decimal(total_cost or 0)
    total_revenue_dec = Decimal(total_revenue or 0)

    shipping_margin = 0.0
    if total_revenue_dec > 0:
        margin_dec = ((total_revenue_dec - total_cost_dec) / total_revenue_dec) * 100
        shipping_margin = float(margin_dec.quantize(Decimal('0.01')))

    return {
        'total_orders': int(total_orders),
        'avg_shipping_cost': float(avg_cost_dec.quantize(Decimal('0.01'))),
        'avg_shipping_revenue': float(avg_revenue_dec.quantize(Decimal('0.01'))),
        'total_shipping_cost': float(total_cost_dec.quantize(Decimal('0.01'))),
        'total_shipping_revenue': float(total_revenue_dec.quantize(Decimal('0.01'))),
        'shipping_margin': shipping_margin,
    }


# Análises Avançadas de Clientes
# ================================

def calculate_rfm_analysis(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> List[Dict]:
    """
    Análise RFM (Recency, Frequency, Monetary) dos clientes.
    Retorna segmentação de clientes baseada em:
    - Recency: dias desde a última compra
    - Frequency: número de compras
    - Monetary: valor total gasto
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    # Buscar apenas vendas válidas com comprador identificado
    rows = (
        query.filter(Sale.comprador.isnot(None))
        .filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .with_entities(
            Sale.comprador,
            Sale.data_venda,
            Sale.valor_total_venda,
        )
        .all()
    )

    if not rows:
        return []

    # Agrupar por cliente
    customer_data: Dict[str, Dict] = {}
    for comprador, data_venda, valor in rows:
        normalized = _normalize_status(comprador)

        if comprador not in customer_data:
            customer_data[comprador] = {
                'last_purchase': data_venda,
                'first_purchase': data_venda,
                'purchases': [],
                'total_value': Decimal(0),
            }

        customer_data[comprador]['purchases'].append(data_venda)
        if data_venda > customer_data[comprador]['last_purchase']:
            customer_data[comprador]['last_purchase'] = data_venda
        if data_venda < customer_data[comprador]['first_purchase']:
            customer_data[comprador]['first_purchase'] = data_venda

        valor_decimal = valor if isinstance(valor, Decimal) else Decimal(valor or 0)
        customer_data[comprador]['total_value'] += valor_decimal

    # Calcular métricas RFM
    reference_date = end if end else datetime.now().date()
    rfm_data = []

    for comprador, data in customer_data.items():
        recency = (reference_date - data['last_purchase']).days
        frequency = len(data['purchases'])
        monetary = float(data['total_value'].quantize(Decimal('0.01')))

        rfm_data.append({
            'comprador': comprador,
            'recency': recency,
            'frequency': frequency,
            'monetary': monetary,
            'first_purchase': data['first_purchase'],
            'last_purchase': data['last_purchase'],
        })

    if not rfm_data:
        return []

    # Calcular quartis para scoring
    recencies = sorted([r['recency'] for r in rfm_data])
    frequencies = sorted([r['frequency'] for r in rfm_data])
    monetaries = sorted([r['monetary'] for r in rfm_data])

    def get_quartile_score(value, sorted_values, reverse=False):
        """Retorna score de 1-4 baseado em quartis."""
        if not sorted_values:
            return 2

        q1_idx = len(sorted_values) // 4
        q2_idx = len(sorted_values) // 2
        q3_idx = 3 * len(sorted_values) // 4

        q1 = sorted_values[q1_idx]
        q2 = sorted_values[q2_idx]
        q3 = sorted_values[q3_idx]

        if reverse:  # Para recency, menor é melhor
            if value <= q1:
                return 4
            elif value <= q2:
                return 3
            elif value <= q3:
                return 2
            else:
                return 1
        else:  # Para frequency e monetary, maior é melhor
            if value >= q3:
                return 4
            elif value >= q2:
                return 3
            elif value >= q1:
                return 2
            else:
                return 1

    # Calcular scores e segmentos
    for customer in rfm_data:
        r_score = get_quartile_score(customer['recency'], recencies, reverse=True)
        f_score = get_quartile_score(customer['frequency'], frequencies)
        m_score = get_quartile_score(customer['monetary'], monetaries)

        customer['r_score'] = r_score
        customer['f_score'] = f_score
        customer['m_score'] = m_score
        customer['rfm_score'] = f"{r_score}{f_score}{m_score}"

        # Segmentação de clientes
        if r_score >= 4 and f_score >= 4:
            segment = 'Champions'
        elif r_score >= 3 and f_score >= 3:
            segment = 'Loyal Customers'
        elif r_score >= 4 and f_score <= 2:
            segment = 'New Customers'
        elif r_score >= 3 and f_score <= 2:
            segment = 'Potential Loyalists'
        elif r_score <= 2 and f_score >= 3:
            segment = 'At Risk'
        elif r_score <= 2 and f_score >= 4:
            segment = 'Cannot Lose Them'
        elif r_score <= 1:
            segment = 'Lost'
        else:
            segment = 'Others'

        customer['segment'] = segment

    # Ordenar por valor monetário (maiores clientes primeiro)
    rfm_data.sort(key=lambda x: x['monetary'], reverse=True)

    return rfm_data


def cohort_analysis(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, any]:
    """
    Análise de Cohort baseada no mês da primeira compra.
    Retorna matriz de retenção mostrando quantos clientes de cada cohort
    continuaram comprando nos meses seguintes.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    # Buscar vendas válidas com comprador identificado
    rows = (
        query.filter(Sale.comprador.isnot(None))
        .filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .with_entities(
            Sale.comprador,
            Sale.data_venda,
        )
        .all()
    )

    if not rows:
        return {
            'cohort_labels': [],
            'period_labels': [],
            'retention_matrix': [],
            'cohort_sizes': [],
        }

    # Agrupar compras por cliente
    customer_purchases: Dict[str, List[date]] = defaultdict(list)
    for comprador, data_venda in rows:
        customer_purchases[comprador].append(data_venda)

    # Determinar primeira compra de cada cliente (cohort)
    customer_cohorts: Dict[str, Tuple[int, int]] = {}  # comprador -> (year, month)
    for comprador, purchases in customer_purchases.items():
        first_purchase = min(purchases)
        customer_cohorts[comprador] = _month_key(first_purchase)

    # Construir matriz de retenção
    cohort_data: Dict[Tuple[int, int], Dict[int, set]] = defaultdict(lambda: defaultdict(set))

    for comprador, purchases in customer_purchases.items():
        cohort = customer_cohorts[comprador]
        cohort_year, cohort_month = cohort

        for purchase_date in purchases:
            # Calcular quantos meses desde a primeira compra
            purchase_year, purchase_month = _month_key(purchase_date)

            # Diferença em meses
            months_diff = (purchase_year - cohort_year) * 12 + (purchase_month - cohort_month)

            cohort_data[cohort][months_diff].add(comprador)

    # Preparar resultado
    sorted_cohorts = sorted(cohort_data.keys())

    if not sorted_cohorts:
        return {
            'cohort_labels': [],
            'period_labels': [],
            'retention_matrix': [],
            'cohort_sizes': [],
        }

    # Determinar número máximo de períodos
    max_periods = 0
    for cohort in sorted_cohorts:
        max_period = max(cohort_data[cohort].keys()) if cohort_data[cohort] else 0
        max_periods = max(max_periods, max_period)

    # Construir matriz de retenção
    cohort_labels = [f"{month:02d}/{year}" for year, month in sorted_cohorts]
    period_labels = [f"Mês {i}" for i in range(max_periods + 1)]
    retention_matrix = []
    cohort_sizes = []

    for cohort in sorted_cohorts:
        cohort_size = len(cohort_data[cohort][0]) if 0 in cohort_data[cohort] else 0
        cohort_sizes.append(cohort_size)

        retention_row = []
        for period in range(max_periods + 1):
            if cohort_size > 0 and period in cohort_data[cohort]:
                retention_count = len(cohort_data[cohort][period])
                retention_rate = round((retention_count / cohort_size) * 100, 2)
                retention_row.append(retention_rate)
            else:
                retention_row.append(0.0)

        retention_matrix.append(retention_row)

    return {
        'cohort_labels': cohort_labels,
        'period_labels': period_labels,
        'retention_matrix': retention_matrix,
        'cohort_sizes': cohort_sizes,
    }


def revenue_composition(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, float]:
    """
    Retorna composição detalhada da receita e custos.
    Útil para gráficos waterfall mostrando o fluxo do lucro.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .with_entities(
            func.sum(Sale.receita_produtos).label('receita_produtos'),
            func.sum(Sale.receita_envio).label('receita_envio'),
            func.sum(Sale.receita_acrescimo_preco).label('acrescimos'),
            func.sum(Sale.taxa_parcelamento).label('taxa_parcelamento'),
            func.sum(Sale.tarifa_venda_impostos).label('tarifas'),
            func.sum(Sale.custo_envio).label('custo_envio'),
            func.sum(Sale.custo_diferencas_peso).label('custo_diferencas'),
            func.sum(Sale.cancelamentos_reembolsos).label('reembolsos'),
            func.sum(Sale.lucro_liquido).label('lucro_liquido'),
        )
        .first()
    )

    if not rows or not rows[0]:
        return {
            'receita_produtos': 0.0,
            'receita_envio': 0.0,
            'acrescimos': 0.0,
            'taxa_parcelamento': 0.0,
            'tarifas': 0.0,
            'custo_envio': 0.0,
            'custo_diferencas': 0.0,
            'reembolsos': 0.0,
            'lucro_liquido': 0.0,
            'receita_total': 0.0,
            'custos_totais': 0.0,
        }

    (receita_produtos, receita_envio, acrescimos, taxa_parcelamento,
     tarifas, custo_envio, custo_diferencas, reembolsos, lucro_liquido) = rows

    # Converter tudo para Decimal
    receita_produtos_dec = Decimal(receita_produtos or 0)
    receita_envio_dec = Decimal(receita_envio or 0)
    acrescimos_dec = Decimal(acrescimos or 0)
    taxa_parcelamento_dec = abs(Decimal(taxa_parcelamento or 0))
    tarifas_dec = abs(Decimal(tarifas or 0))
    custo_envio_dec = abs(Decimal(custo_envio or 0))
    custo_diferencas_dec = abs(Decimal(custo_diferencas or 0))
    reembolsos_dec = abs(Decimal(reembolsos or 0))

    receita_total = receita_produtos_dec + receita_envio_dec + acrescimos_dec
    custos_totais = (taxa_parcelamento_dec + tarifas_dec + custo_envio_dec +
                     custo_diferencas_dec + reembolsos_dec)

    return {
        'receita_produtos': float(receita_produtos_dec.quantize(Decimal('0.01'))),
        'receita_envio': float(receita_envio_dec.quantize(Decimal('0.01'))),
        'acrescimos': float(acrescimos_dec.quantize(Decimal('0.01'))),
        'taxa_parcelamento': float(taxa_parcelamento_dec.quantize(Decimal('0.01'))),
        'tarifas': float(tarifas_dec.quantize(Decimal('0.01'))),
        'custo_envio': float(custo_envio_dec.quantize(Decimal('0.01'))),
        'custo_diferencas': float(custo_diferencas_dec.quantize(Decimal('0.01'))),
        'reembolsos': float(reembolsos_dec.quantize(Decimal('0.01'))),
        'lucro_liquido': float((receita_total - custos_totais).quantize(Decimal('0.01'))),
        'receita_total': float(receita_total.quantize(Decimal('0.01'))),
        'custos_totais': float(custos_totais.quantize(Decimal('0.01'))),
    }


def margin_evolution(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List]:
    """
    Retorna evolução da margem de lucro ao longo do tempo (mensal).
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .filter(Sale.margem_percentual.isnot(None))
        .with_entities(
            Sale.data_venda,
            Sale.margem_percentual,
            Sale.lucro_liquido,
        )
        .all()
    )

    if not rows:
        return {'labels': [], 'margins': [], 'profits': []}

    # Agrupar por mês
    monthly_data: Dict[Tuple[int, int], Dict] = defaultdict(
        lambda: {'margin_sum': Decimal(0), 'profit_sum': Decimal(0), 'count': 0}
    )

    for data_venda, margem, lucro in rows:
        month_key = _month_key(data_venda)
        margem_dec = margem if isinstance(margem, Decimal) else Decimal(margem or 0)
        lucro_dec = lucro if isinstance(lucro, Decimal) else Decimal(lucro or 0)

        monthly_data[month_key]['margin_sum'] += margem_dec
        monthly_data[month_key]['profit_sum'] += lucro_dec
        monthly_data[month_key]['count'] += 1

    # Ordenar e calcular médias
    sorted_months = sorted(monthly_data.keys())
    labels = [f"{month:02d}/{year}" for year, month in sorted_months]
    margins = []
    profits = []

    for month_key in sorted_months:
        data = monthly_data[month_key]
        avg_margin = data['margin_sum'] / data['count'] if data['count'] > 0 else Decimal(0)
        margins.append(float(avg_margin.quantize(Decimal('0.01'))))
        profits.append(float(data['profit_sum'].quantize(Decimal('0.01'))))

    return {
        'labels': labels,
        'margins': margins,
        'profits': profits,
    }


def quarterly_sales(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
) -> Dict[str, List]:
    """
    Retorna vendas agrupadas por trimestre.
    """
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.filter(Sale.status_pedido.in_(list(VALID_STATUSES)))
        .with_entities(
            Sale.data_venda,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total'),
        )
        .group_by(Sale.data_venda)
        .all()
    )

    # Agrupar por trimestre
    quarterly_data: Dict[Tuple[int, int], Decimal] = defaultdict(lambda: Decimal(0))

    for data_venda, total in rows:
        year = data_venda.year
        quarter = (data_venda.month - 1) // 3 + 1  # 1-4
        total_dec = total if isinstance(total, Decimal) else Decimal(total or 0)
        quarterly_data[(year, quarter)] += total_dec

    # Ordenar e formatar
    sorted_quarters = sorted(quarterly_data.keys())
    labels = [f"Q{q}/{y}" for y, q in sorted_quarters]
    values = [float(quarterly_data[key].quantize(Decimal('0.01'))) for key in sorted_quarters]

    return {
        'labels': labels,
        'values': values,
    }
