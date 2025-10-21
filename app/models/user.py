from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))

    # RBAC: roles disponíveis
    role = db.Column(db.String(20), nullable=False, default='cliente', index=True)
    # Roles: 'gestor', 'analista', 'cliente'

    # Multi-tenant: relacionamento com empresa
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)

    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

    # Métodos de verificação de permissões
    def is_gestor(self):
        """Verifica se o usuário é gestor (admin)"""
        return self.role == 'gestor'

    def is_analista(self):
        """Verifica se o usuário é analista"""
        return self.role == 'analista'

    def is_cliente(self):
        """Verifica se o usuário é cliente"""
        return self.role == 'cliente'

    def can_manage_companies(self):
        """Verifica se pode gerenciar empresas (criar/editar/deletar)"""
        return self.is_gestor()

    def can_view_all_companies(self):
        """Verifica se pode visualizar todas as empresas"""
        return self.is_gestor() or self.is_analista()

    def get_accessible_companies(self):
        """Retorna as empresas que o usuário pode acessar"""
        from app.models.company import Company

        if self.can_view_all_companies():
            return Company.query.filter_by(is_active=True).all()
        elif self.is_cliente() and self.company_id:
            return [self.company]
        return []

    def to_dict(self):
        """Serializa o modelo para JSON"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'company_id': self.company_id,
            'company_name': self.company.name if self.company else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }