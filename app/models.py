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
    manager_notes = db.relationship(
        'ManagerNote',
        backref='author',
        lazy=True,
        foreign_keys='ManagerNote.author_id',
    )

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
    company_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    nome_produto = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(120), nullable=False, index=True)
    status_pedido = db.Column(db.String(50), nullable=False, index=True)
    data_venda = db.Column(db.Date, nullable=False, index=True, default=date.today)
    valor_total_venda = db.Column(db.Numeric(12, 2), nullable=False)

    company = db.relationship('User', foreign_keys=[company_id], backref=db.backref('sales', lazy=True))

    def __repr__(self):
        return f'<Sale {self.sku} {self.valor_total_venda}>'


class ManagerNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

    def __repr__(self):
        return f'<ManagerNote {self.periodo_inicio} - {self.periodo_fim}>'
