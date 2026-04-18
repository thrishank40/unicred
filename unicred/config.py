import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Use strong fallback if env is missing, but warn in production
    SECRET_KEY = os.environ.get('SECRET_KEY', 'unicred-super-secret-key-2024')
    DEBUG = os.environ.get('FLASK_ENV', 'development') == 'development'
    
    # MySQL Configuration
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'unicred')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    
    # Mail Configuration — disabled for this development phase (email verification removed)
    # Re-enable these and restore flask_mail when email verification is needed again.
    # MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    # MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    # MAIL_USE_TLS = True
    # MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    # MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    # MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@unicred.edu')
    
    # App Settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Security
    CREDIT_INITIAL_BALANCE = 100
    MIN_TRUST_SCORE = 3.0
    PENALTY_PER_DAY = 5
    MAX_VIOLATIONS = 3
    
    # WTForms / CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', 'csrf-secret-key-2024')
    
    # Rate Limiting
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = "memory://"
    
    # Session
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = 7200  # 2 hours
