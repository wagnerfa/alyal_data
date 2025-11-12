from datetime import date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user' ou 'manager'
    logo_filename = db.Column(db.String(255))
    manager_notes = db.relationship('ManagerNote', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_manager(self):
        return self.role == 'manager'

    def __repr__(self):
        return f'<User {self.username}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Marketplace(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    sales = db.relationship('Sale', backref='marketplace', lazy=True)

    def __repr__(self):
        return f'<Marketplace {self.nome}>'


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    marketplace_id = db.Column(db.Integer, db.ForeignKey('marketplace.id'), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)

    # Colunas originais
    nome_produto = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(120), nullable=False, index=True)
    status_pedido = db.Column(db.String(50), nullable=False, index=True)
    data_venda = db.Column(db.Date, nullable=False, index=True, default=date.today)
    valor_total_venda = db.Column(db.Numeric(12, 2), nullable=False)

    # Colunas de Dados do Pedido
    numero_pedido = db.Column(db.String(100), nullable=True, index=True)
    titulo_anuncio = db.Column(db.String(500), nullable=True)
    numero_anuncio = db.Column(db.String(100), nullable=True)
    unidades = db.Column(db.Integer, nullable=True)

    # Colunas de Cliente
    comprador = db.Column(db.String(255), nullable=True, index=True)
    cpf_comprador = db.Column(db.String(20), nullable=True)

    # Colunas Financeiras
    total_brl = db.Column(db.Numeric(12, 2), nullable=True)
    receita_produtos = db.Column(db.Numeric(12, 2), nullable=True)
    receita_acrescimo_preco = db.Column(db.Numeric(12, 2), nullable=True)
    taxa_parcelamento = db.Column(db.Numeric(12, 2), nullable=True)
    tarifa_venda_impostos = db.Column(db.Numeric(12, 2), nullable=True)
    receita_envio = db.Column(db.Numeric(12, 2), nullable=True)
    tarifas_envio = db.Column(db.Numeric(12, 2), nullable=True)
    custo_envio = db.Column(db.Numeric(12, 2), nullable=True)
    custo_diferencas_peso = db.Column(db.Numeric(12, 2), nullable=True)
    cancelamentos_reembolsos = db.Column(db.Numeric(12, 2), nullable=True)
    preco_unitario = db.Column(db.Numeric(12, 2), nullable=True)

    # Colunas Geográficas
    estado_comprador = db.Column(db.String(50), nullable=True, index=True)
    cidade_comprador = db.Column(db.String(100), nullable=True, index=True)

    # Colunas de Envio
    forma_entrega = db.Column(db.String(100), nullable=True)

    # Colunas Calculadas/Derivadas
    lucro_liquido = db.Column(db.Numeric(12, 2), nullable=True)
    margem_percentual = db.Column(db.Numeric(5, 2), nullable=True)
    faixa_preco = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Sale {self.sku} {self.valor_total_venda}>'


class ManagerNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<ManagerNote {self.periodo_inicio} - {self.periodo_fim}>'
