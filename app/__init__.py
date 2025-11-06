from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    
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

    # Criar tabelas do banco de dados
    with app.app_context():
        db.create_all()
        # Criar usuário admin padrão se não existir
        from app.models import User, Marketplace
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

        default_marketplaces = ['Mercado Livre', 'Shopee', 'Amazon', 'Magalu']
        for marketplace_name in default_marketplaces:
            if not Marketplace.query.filter_by(nome=marketplace_name).first():
                db.session.add(Marketplace(nome=marketplace_name))
        db.session.commit()

    return app
