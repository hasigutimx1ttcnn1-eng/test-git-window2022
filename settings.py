import os
from pathlib import Path
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# --- セキュリティ設定 ---
# .envに設定がある場合はそれを使用し、なければデフォルト値（危険なため本番は.env必須）を使用
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-for-dev')

# 本番環境では .env で DEBUG=False にすることを強く推奨
#DEBUG = os.getenv('DEBUG', 'False') == 'True'
DEBUG = True
# 許可するホスト名（ドメインを追加）
#raw_hosts = os.getenv('ALLOWED_HOSTS', '162.43.23.120,localhost,127.0.0.1,mec-corp-tools.online')
#ALLOWED_HOSTS = [host.strip() for host in raw_hosts.split(',') if host.strip()]

# CSRF信頼済みオリジン（HTTPS化したドメインを追加）
#raw_origins = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://162.43.23.120:8080,https://mec-corp-tools.online,http://mec-corp-tools.online')
#CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]

# 環境変数は使わず、一旦直接リストで指定する
#ALLOWED_HOSTS = [
#    'mec-corp-tools.online',
#    '162.43.23.120',
#    'localhost',
#    '127.0.0.1',
#]
ALLOWED_HOSTS = ['*']

# CSRFの設定も http 版を確実に含める
CSRF_TRUSTED_ORIGINS = [
    'http://mec-corp-tools.online',
    'https://mec-corp-tools.online',
    'http://162.43.23.120:8000',
]


# HTTPS化に伴うプロキシ設定（NginxでHTTPSを受け取る場合に必要）
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# --- アプリケーション定義 ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'societies',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# --- データベース設定 ---
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.sqlite3')
DB_NAME = os.getenv('DB_NAME', 'db.sqlite3')
DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': BASE_DIR / DB_NAME if DB_ENGINE == 'django.db.backends.sqlite3' else DB_NAME,
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', ''),
    }
}


# --- パスワードバリデーション ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# --- 国際化設定 ---
LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True


# --- 静的ファイル設定 ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    # os.path.join(BASE_DIR, 'static'), # 必要に応じて有効化
]


# --- その他カスタム設定 ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = '/accounts/login/'

TEAMS_WEBHOOK_URLS = {
    '制作部': 'https://defaultfbf6eb54e6284c4089dfcec326d8b7.21.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/ef86b41d808a49e088cdf9e816be00a6/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=sn7iuuT-En8qQcvp5WGpvVOHY2HagPpTaGj422l3e50',
    '予備校部': 'https://defaultfbf6eb54e6284c4089dfcec326d8b7.21.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/1496ac88eb954df7a23d3bd0d38a52be/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=7j79GgCNw4xDJnzf5rN4NBqmt6pWOCQHsdH8bf42RTI',
}