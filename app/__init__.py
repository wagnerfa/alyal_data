import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

from app.utils.formatting import format_currency_br, format_decimal_br
from sqlalchemy import inspect, text

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Inicializar extensões
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Registrar blueprints
    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.data import data_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(data_bp)

    app.jinja_env.filters['currency_br'] = format_currency_br
    app.jinja_env.filters['decimal_br'] = format_decimal_br

    # Criar tabelas do banco de dados
    with app.app_context():
        db.create_all()
        # Criar usuário admin padrão se não existir
        from app.models import User, Marketplace
        inspector = inspect(db.engine)
        user_columns = {col['name'] for col in inspector.get_columns('user')}
        if 'logo_filename' not in user_columns:
            try:
                db.session.execute(text('ALTER TABLE user ADD COLUMN logo_filename VARCHAR(255)'))
                db.session.commit()
            except Exception:
                db.session.rollback()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com', role='manager')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

        if not User.query.filter_by(username='user').first():
            user = User(username='user', email='user@example.com', role='user')
            user.set_password('user123')
            db.session.add(user)
            db.session.commit()

        sale_columns = {col['name'] for col in inspector.get_columns('sale')}
        if 'company_id' not in sale_columns:
            try:
                db.session.execute(text('ALTER TABLE sale ADD COLUMN company_id INTEGER'))
                db.session.commit()
            except Exception:
                db.session.rollback()
            else:
                sale_columns.add('company_id')

        if 'company_id' in sale_columns:
            default_company = (
                User.query.filter_by(role='user')
                .order_by(User.id.asc())
                .first()
            )
            if default_company:
                try:
                    db.session.execute(
                        text('UPDATE sale SET company_id = :company_id WHERE company_id IS NULL'),
                        {'company_id': default_company.id},
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()

        default_marketplaces = ['Mercado Livre', 'Shopee', 'Amazon', 'Magalu']
        for marketplace_name in default_marketplaces:
            if not Marketplace.query.filter_by(nome=marketplace_name).first():
                db.session.add(Marketplace(nome=marketplace_name))
        db.session.commit()

    return app
