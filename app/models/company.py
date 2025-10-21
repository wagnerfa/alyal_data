from app import db
from datetime import datetime


class Company(db.Model):
    """Modelo de Empresa/Loja do cliente"""
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    cnpj = db.Column(db.String(18), unique=True, nullable=True, index=True)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamento com usuários (clientes da empresa)
    users = db.relationship('User', backref='company', lazy='dynamic')

    def __repr__(self):
        return f'<Company {self.name}>'

    def to_dict(self):
        """Serializa o modelo para JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'cnpj': self.cnpj,
            'email': self.email,
            'phone': self.phone,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'clients_count': self.users.filter_by(role='cliente').count()
        }

    @property
    def clients(self):
        """Retorna apenas os clientes (não gestores/analistas)"""
        return self.users.filter_by(role='cliente')
