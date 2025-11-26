"""
Adaptadores para processar arquivos nativos de cada marketplace.

Cada adaptador converte o formato específico do marketplace para o schema unificado do sistema.
Suporta: Mercado Livre (CSV) e Shopee (XLSX).
"""

import csv
import io
import re
import unicodedata
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

import openpyxl


# Mapeamento de meses em português para números
MESES_PT = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
}


def detect_encoding(raw_bytes: bytes) -> str:
    """
    Detecta encoding do arquivo tentando decodificar com diferentes encodings.

    Returns:
        Nome do encoding detectado
    """
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    for enc in encodings:
        try:
            raw_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'utf-8'


def parse_decimal_ptbr(value: str) -> Optional[Decimal]:
    """
    Parse valores decimais em formato brasileiro (vírgula como separador decimal).

    Exemplos:
        "1.234,56" -> Decimal("1234.56")
        "R$ 100,00" -> Decimal("100.00")
        "-50,25" -> Decimal("-50.25")
    """
    if not value or not isinstance(value, str):
        return None

    # Remover símbolos de moeda e espaços
    cleaned = value.strip().replace('R$', '').replace(' ', '').replace('\u00a0', '')

    if not cleaned or cleaned == '-':
        return None

    try:
        # Se tem vírgula e ponto, o ponto é separador de milhar
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        # Se tem apenas vírgula, é separador decimal
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        # Se tem apenas ponto, verificar se é milhar ou decimal
        elif '.' in cleaned:
            # Se tem mais de um ponto, é separador de milhar
            if cleaned.count('.') > 1:
                cleaned = cleaned.replace('.', '')
            # Se o ponto está a 3 posições do final, pode ser milhar
            elif len(cleaned.split('.')[-1]) == 3 and len(cleaned.split('.')[0]) <= 3:
                # Assumir que é milhar apenas se parte inteira tem 1-3 dígitos
                cleaned = cleaned.replace('.', '')

        return Decimal(cleaned)
    except (ValueError, InvalidOperation):
        return None


class MercadoLivreAdapter:
    """
    Adaptador para processar relatórios de vendas do Mercado Livre.

    Formato esperado: CSV com encoding latin-1, delimitador ";", 60+ colunas
    """

    # Mapeamento de colunas ML -> Schema do sistema
    COLUMN_MAP = {
        'N.º de venda': 'numero_pedido',
        'Data da venda': 'data_venda',
        'Descrição do status': 'status_pedido',
        'SKU': 'sku',
        'Título do anúncio': 'titulo_anuncio',
        '# de anúncio': 'numero_anuncio',
        'Unidades': 'unidades',
        'Comprador': 'comprador',
        'CPF': 'cpf_comprador',
        'Total (BRL)': 'total_brl',
        'Receita por produtos (BRL)': 'receita_produtos',
        'Receita por acréscimo no preço (pago pelo comprador)': 'receita_acrescimo_preco',
        'Taxa de parcelamento equivalente ao acréscimo': 'taxa_parcelamento',
        'Tarifa de venda e impostos (BRL)': 'tarifa_venda_impostos',
        'Receita por envio (BRL)': 'receita_envio',
        'Tarifas de envio (BRL)': 'tarifas_envio',
        'Custo de envio com base nas medidas e peso declarados': 'custo_envio',
        'Custo por diferenças nas medidas e no peso do pacote': 'custo_diferencas_peso',
        'Cancelamentos e reembolsos (BRL)': 'cancelamentos_reembolsos',
        'Preço unitário de venda do anúncio (BRL)': 'preco_unitario',
        'Estado': 'estado_comprador',
        'Cidade': 'cidade_comprador',
        'Forma de entrega': 'forma_entrega',
    }

    # Mapeamento de status ML -> padrão do sistema
    STATUS_MAP = {
        'entregue': 'entregue',
        'a caminho': 'enviado',
        'preparando': 'pago',
        'cancelado': 'cancelado',
        'pacote cancelado pelo mercado livre': 'cancelado',
        'pagamento aprovado': 'pago',
        'pronto para envio': 'pago',
        'em preparação': 'pago',
    }

    @staticmethod
    def detect(headers: List[str]) -> bool:
        """
        Detecta se é arquivo do Mercado Livre baseado nos headers.

        Returns:
            True se for arquivo do Mercado Livre
        """
        ml_indicators = ['N.º de venda', 'Tarifa de venda e impostos', '# de anúncio']
        return sum(1 for h in ml_indicators if h in headers) >= 2

    @staticmethod
    def parse_date(date_str: str) -> Optional[date]:
        """
        Parse data do Mercado Livre.

        Formatos aceitos:
            "31 de outubro de 2025 23:59 hs."
            "01 de janeiro de 2025 10:30"
            "2025-10-31"
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Formato ISO: 2025-10-31
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            try:
                return datetime.strptime(date_str[:10], '%Y-%m-%d').date()
            except ValueError:
                pass

        # Formato verbose: "31 de outubro de 2025 23:59 hs."
        pattern = r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})'
        match = re.search(pattern, date_str, re.IGNORECASE)

        if match:
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))

            # Remover acentos do nome do mês
            month_name = unicodedata.normalize('NFKD', month_name)
            month_name = ''.join(c for c in month_name if not unicodedata.combining(c))

            month = MESES_PT.get(month_name)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        return None

    @staticmethod
    def normalize_status(status: str) -> str:
        """
        Normaliza status do ML para padrão do sistema.

        Returns:
            Status normalizado: 'pago', 'enviado', 'entregue', 'cancelado'
        """
        if not status:
            return 'pago'

        # Normalizar: lowercase, remover acentos
        normalized = unicodedata.normalize('NFKD', status.lower().strip())
        normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

        return MercadoLivreAdapter.STATUS_MAP.get(normalized, 'pago')

    @staticmethod
    def process_row(row: Dict[str, str]) -> Optional[Dict]:
        """
        Converte uma linha do ML para schema do sistema.

        Returns:
            Dict com dados normalizados ou None se inválido
        """
        normalized = {}

        # Mapear colunas
        for ml_col, sys_col in MercadoLivreAdapter.COLUMN_MAP.items():
            if ml_col not in row:
                continue

            value = row[ml_col]

            # Aplicar transformações específicas por tipo de campo
            if sys_col == 'data_venda':
                value = MercadoLivreAdapter.parse_date(value)
                if not value:
                    return None  # Data inválida, pular linha

            elif sys_col == 'status_pedido':
                value = MercadoLivreAdapter.normalize_status(value)

            elif sys_col in ['total_brl', 'receita_produtos', 'receita_acrescimo_preco',
                            'taxa_parcelamento', 'tarifa_venda_impostos', 'receita_envio',
                            'tarifas_envio', 'custo_envio', 'custo_diferencas_peso',
                            'cancelamentos_reembolsos', 'preco_unitario']:
                value = parse_decimal_ptbr(value)

            elif sys_col == 'unidades':
                try:
                    value = int(value) if value and value.strip() else None
                except ValueError:
                    value = None

            elif sys_col in ['sku', 'numero_pedido', 'titulo_anuncio', 'numero_anuncio',
                            'comprador', 'cpf_comprador', 'estado_comprador',
                            'cidade_comprador', 'forma_entrega']:
                value = value.strip() if value else None

            normalized[sys_col] = value

        # Campos obrigatórios
        if not normalized.get('sku'):
            return None

        # Preencher campos derivados
        normalized['nome_produto'] = normalized.get('titulo_anuncio') or normalized.get('sku')
        normalized['valor_total_venda'] = normalized.get('total_brl') or Decimal(0)

        # Calcular faixa de preço
        preco = normalized.get('preco_unitario') or normalized.get('valor_total_venda')
        if preco:
            if preco < Decimal('50'):
                normalized['faixa_preco'] = 'Baixo'
            elif preco <= Decimal('200'):
                normalized['faixa_preco'] = 'Médio'
            else:
                normalized['faixa_preco'] = 'Alto'

        # Calcular lucro e margem
        receita_produtos = normalized.get('receita_produtos')
        if receita_produtos and receita_produtos > 0:
            custos = Decimal(0)
            for field in ['taxa_parcelamento', 'tarifa_venda_impostos', 'custo_envio',
                         'custo_diferencas_peso', 'cancelamentos_reembolsos']:
                if normalized.get(field):
                    custos += abs(normalized[field])

            lucro_liquido = receita_produtos - custos
            margem_percentual = (lucro_liquido / receita_produtos) * Decimal(100)

            normalized['lucro_liquido'] = lucro_liquido
            normalized['margem_percentual'] = margem_percentual

        return normalized

    @staticmethod
    def parse_file(raw_bytes: bytes) -> Tuple[List[Dict], List[str]]:
        """
        Processa arquivo CSV do Mercado Livre.

        Returns:
            Tuple (lista de dicts normalizados, lista de erros)
        """
        encoding = detect_encoding(raw_bytes)
        text_stream = io.TextIOWrapper(io.BytesIO(raw_bytes), encoding=encoding, newline='')

        # Detectar delimitador
        sample = text_stream.read(2048)
        text_stream.seek(0)

        delimiter = ';'
        if sample.count(',') > sample.count(';'):
            delimiter = ','

        reader = csv.DictReader(text_stream, delimiter=delimiter)

        parsed_data = []
        errors = []

        for line_num, row in enumerate(reader, start=2):
            try:
                normalized = MercadoLivreAdapter.process_row(row)
                if normalized:
                    parsed_data.append(normalized)
                else:
                    errors.append(f"Linha {line_num}: Dados obrigatórios faltando (SKU ou Data)")
            except Exception as e:
                errors.append(f"Linha {line_num}: Erro ao processar - {str(e)}")

        return parsed_data, errors


class ShopeeAdapter:
    """
    Adaptador para processar relatórios de vendas da Shopee.

    Formato esperado: XLSX
    """

    # Mapeamento de colunas Shopee -> Schema do sistema
    COLUMN_MAP = {
        'ID do pedido': 'numero_pedido',
        'Status do pedido': 'status_pedido',
        'Data de criação do pedido': 'data_venda',
        'Nº de referência do SKU principal': 'sku',
        'Nome do Produto': 'nome_produto',
        'Nome da variação': 'titulo_anuncio',
        'Quantidade': 'unidades',
        'Preço acordado': 'preco_unitario',
        'Subtotal do produto': 'receita_produtos',
        'Total do pedido': 'total_brl',
        'Cidade': 'cidade_comprador',
        'Estado': 'estado_comprador',
    }

    # Mapeamento de status Shopee -> padrão do sistema
    STATUS_MAP = {
        'concluído': 'entregue',
        'concluido': 'entregue',
        'em andamento': 'enviado',
        'cancelado': 'cancelado',
        'aguardando coleta': 'pago',
        'processando': 'pago',
        'enviado': 'enviado',
        'entregue': 'entregue',
    }

    @staticmethod
    def detect(headers: List[str]) -> bool:
        """
        Detecta se é arquivo da Shopee baseado nos headers.

        Returns:
            True se for arquivo da Shopee
        """
        shopee_indicators = ['ID do pedido', 'Nº de referência do SKU principal', 'Status do pedido']
        return sum(1 for h in shopee_indicators if h in headers) >= 2

    @staticmethod
    def parse_date(date_str) -> Optional[date]:
        """
        Parse data da Shopee.

        Formatos aceitos:
            "2025-01-01 00:30"
            "2025-01-01"
            datetime object (do Excel)
        """
        if isinstance(date_str, datetime):
            return date_str.date()

        if isinstance(date_str, date):
            return date_str

        if not date_str or not isinstance(date_str, str):
            return None

        date_str = date_str.strip()

        # Tentar formatos comuns
        for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    @staticmethod
    def normalize_status(status: str) -> str:
        """
        Normaliza status da Shopee para padrão do sistema.

        Returns:
            Status normalizado: 'pago', 'enviado', 'entregue', 'cancelado'
        """
        if not status:
            return 'pago'

        # Normalizar: lowercase, remover acentos
        normalized = unicodedata.normalize('NFKD', status.lower().strip())
        normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

        return ShopeeAdapter.STATUS_MAP.get(normalized, 'pago')

    @staticmethod
    def process_row(row: Dict) -> Optional[Dict]:
        """
        Converte uma linha da Shopee para schema do sistema.

        Returns:
            Dict com dados normalizados ou None se inválido
        """
        normalized = {}

        # Mapear colunas
        for shopee_col, sys_col in ShopeeAdapter.COLUMN_MAP.items():
            if shopee_col not in row:
                continue

            value = row[shopee_col]

            # Aplicar transformações específicas
            if sys_col == 'data_venda':
                value = ShopeeAdapter.parse_date(value)
                if not value:
                    return None  # Data inválida

            elif sys_col == 'status_pedido':
                value = ShopeeAdapter.normalize_status(value)

            elif sys_col in ['preco_unitario', 'receita_produtos', 'total_brl']:
                if isinstance(value, (int, float, Decimal)):
                    value = Decimal(str(value))
                elif isinstance(value, str):
                    value = parse_decimal_ptbr(value)

            elif sys_col == 'unidades':
                try:
                    value = int(value) if value else None
                except (ValueError, TypeError):
                    value = None

            elif isinstance(value, str):
                value = value.strip() if value else None

            normalized[sys_col] = value

        # Campos obrigatórios
        if not normalized.get('sku'):
            return None

        # Preencher campos derivados
        if not normalized.get('nome_produto'):
            normalized['nome_produto'] = normalized.get('titulo_anuncio') or normalized.get('sku')

        if not normalized.get('valor_total_venda'):
            normalized['valor_total_venda'] = normalized.get('total_brl') or Decimal(0)

        # Calcular faixa de preço
        preco = normalized.get('preco_unitario') or normalized.get('valor_total_venda')
        if preco:
            if preco < Decimal('50'):
                normalized['faixa_preco'] = 'Baixo'
            elif preco <= Decimal('200'):
                normalized['faixa_preco'] = 'Médio'
            else:
                normalized['faixa_preco'] = 'Alto'

        return normalized

    @staticmethod
    def parse_file(raw_bytes: bytes) -> Tuple[List[Dict], List[str]]:
        """
        Processa arquivo XLSX da Shopee.

        Returns:
            Tuple (lista de dicts normalizados, lista de erros)
        """
        workbook = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
        sheet = workbook.active

        # Ler headers da primeira linha
        headers = []
        for cell in sheet[1]:
            headers.append(cell.value)

        parsed_data = []
        errors = []

        # Processar linhas
        for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            try:
                # Criar dict da linha
                row_dict = {headers[i]: row[i] for i in range(len(headers)) if i < len(row)}

                normalized = ShopeeAdapter.process_row(row_dict)
                if normalized:
                    parsed_data.append(normalized)
                else:
                    errors.append(f"Linha {row_num}: Dados obrigatórios faltando (SKU ou Data)")
            except Exception as e:
                errors.append(f"Linha {row_num}: Erro ao processar - {str(e)}")

        return parsed_data, errors


def detect_marketplace(headers: List[str]) -> Optional[str]:
    """
    Detecta qual marketplace baseado nos headers do arquivo.

    Returns:
        'mercado_livre', 'shopee' ou None
    """
    if MercadoLivreAdapter.detect(headers):
        return 'mercado_livre'
    elif ShopeeAdapter.detect(headers):
        return 'shopee'
    return None
