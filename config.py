import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads', 'logos')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB (increased for CSV uploads)
    ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
