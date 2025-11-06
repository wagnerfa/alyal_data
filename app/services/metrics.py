from decimal import Decimal
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, func
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


def _apply_common_filters(query, start, end, marketplace_id):
    if start:
        query = query.filter(Sale.data_venda >= start)
    if end:
        query = query.filter(Sale.data_venda <= end)
    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
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


def get_kpis(session: Session, start, end, marketplace_id: Optional[int] = None) -> Dict[str, float]:
    base_query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
    thresholds: Optional[Dict[str, float]] = None,
) -> List[Dict[str, float]]:
    thresholds = thresholds or {'A': 0.8, 'B': 0.95}

    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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


def get_data_boundaries(session: Session, marketplace_id: Optional[int] = None):
    query = session.query(func.min(Sale.data_venda), func.max(Sale.data_venda))
    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
    min_date, max_date = query.first() or (None, None)
    return min_date, max_date


def top_products_by_revenue(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    limit: int = 5,
) -> Dict[str, List]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
) -> Dict[str, List[float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

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
