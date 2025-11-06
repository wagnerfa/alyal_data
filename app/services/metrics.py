from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models import Sale


VALID_STATUSES = {'pago', 'enviado', 'entregue'}
CANCELLED_STATUS = 'cancelado'


def _apply_common_filters(query, start, end, marketplace_id):
    if start:
        query = query.filter(Sale.data_venda >= start)
    if end:
        query = query.filter(Sale.data_venda <= end)
    if marketplace_id:
        query = query.filter(Sale.marketplace_id == marketplace_id)
    return query


def get_kpis(session: Session, start, end, marketplace_id: Optional[int] = None) -> Dict[str, float]:
    base_query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    valid_query = base_query.filter(Sale.status_pedido.in_(VALID_STATUSES))
    faturamento_result = valid_query.with_entities(func.coalesce(func.sum(Sale.valor_total_venda), 0)).scalar()
    faturamento_decimal = faturamento_result if isinstance(faturamento_result, Decimal) else Decimal(faturamento_result or 0)
    pedidos_totais = valid_query.count()

    cancelados = base_query.filter(Sale.status_pedido == CANCELLED_STATUS).count()
    total_considerado = pedidos_totais + cancelados

    ticket_medio = float((faturamento_decimal / pedidos_totais) if pedidos_totais else Decimal(0))
    taxa_cancelamento = float((cancelados / total_considerado) * 100) if total_considerado else 0.0

    return {
        'faturamento': float(faturamento_decimal),
        'pedidos_totais': pedidos_totais,
        'ticket_medio': round(ticket_medio, 2),
        'taxa_cancelamento': round(taxa_cancelamento, 2),
    }


def sales_timeseries(session: Session, start, end, marketplace_id: Optional[int] = None) -> List[Dict[str, float]]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)
    query = query.filter(Sale.status_pedido.in_(VALID_STATUSES))

    rows = (
        query.with_entities(
            Sale.data_venda,
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total')
        )
        .group_by(Sale.data_venda)
        .order_by(Sale.data_venda)
        .all()
    )

    timeseries = []
    for data_venda, total in rows:
        total_decimal = total if isinstance(total, Decimal) else Decimal(total or 0)
        timeseries.append({
            'data': data_venda.isoformat(),
            'faturamento_diario': float(total_decimal),
        })
    return timeseries


def status_breakdown(session: Session, start, end, marketplace_id: Optional[int] = None) -> Dict[str, int]:
    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)

    rows = (
        query.with_entities(
            Sale.status_pedido,
            func.count(Sale.id)
        )
        .group_by(Sale.status_pedido)
        .all()
    )

    return {status: count for status, count in rows}


def abc_by_revenue(
    session: Session,
    start,
    end,
    marketplace_id: Optional[int] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[Dict[str, float]]:
    thresholds = thresholds or {'A': 0.8, 'B': 0.95}

    query = _apply_common_filters(session.query(Sale), start, end, marketplace_id)
    query = query.filter(Sale.status_pedido.in_(VALID_STATUSES))

    rows = (
        query.with_entities(
            Sale.sku,
            func.max(Sale.nome_produto).label('nome_produto'),
            func.coalesce(func.sum(Sale.valor_total_venda), 0).label('total')
        )
        .group_by(Sale.sku)
        .order_by(desc('total'))
        .all()
    )

    total_revenue = sum((row.total if isinstance(row.total, Decimal) else Decimal(row.total or 0)) for row in rows)
    total_revenue = total_revenue or Decimal(0)

    acumulado = Decimal(0)
    resultado = []
    for row in rows:
        faturamento_decimal = row.total if isinstance(row.total, Decimal) else Decimal(row.total or 0)
        percentual = (faturamento_decimal / total_revenue * 100) if total_revenue else Decimal(0)
        acumulado += percentual

        classe = 'C'
        acumulado_ratio = float(acumulado / 100)
        if acumulado_ratio <= thresholds.get('A', 0.8):
            classe = 'A'
        elif acumulado_ratio <= thresholds.get('B', 0.95):
            classe = 'B'

        resultado.append({
            'sku': row.sku,
            'nome_produto': row.nome_produto,
            'faturamento': float(faturamento_decimal),
            'percentual': float(percentual),
            'percentual_acumulado': float(acumulado),
            'classe': classe,
        })

    return resultado
