"""
Django settings for MediaCompile project.
Generated for Phase 2: Authentication and Backend Foundation.
"""

import os
from pathlib import Path
from .env_validation import validate_environment_configuration, ProductionConfigurationError

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent.parent

# Load .env from root directory if present
env_file = ROOT_DIR / '.env'
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                clean_k = k.strip()
                clean_v = v.strip().strip("'\"")
                os.environ.setdefault(clean_k, clean_v)

ENVIRONMENT = os.environ.get('ENVIRONMENT', os.environ.get('NODE_ENV', 'development')).lower()
IS_PRODUCTION = ENVIRONMENT == 'production'

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-prod-evermind')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    
    # Third party apps
    'corsheaders',
    'rest_framework',
    
    # Internal apps
    'users',
    'core',
    'content',
    'chat',
    'integrations',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'core.middleware.SecurityHeadersMiddleware',
    'core.middleware.RequestAuditLoggingMiddleware',
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
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database Configuration (Development Docker pgvector vs External Production PostgreSQL)
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL:
    from urllib.parse import urlparse, parse_qs
    parsed_db = urlparse(DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed_db.path.lstrip('/'),
            'USER': parsed_db.username or '',
            'PASSWORD': parsed_db.password or '',
            'HOST': parsed_db.hostname or '',
            'PORT': str(parsed_db.port or 5432),
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '600' if IS_PRODUCTION else '0')),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {},
        }
    }
    # Parse query parameters such as sslmode
    qs = parse_qs(parsed_db.query)
    if 'sslmode' in qs:
        DATABASES['default']['OPTIONS']['sslmode'] = qs['sslmode'][0]
    elif IS_PRODUCTION:
        DATABASES['default']['OPTIONS']['sslmode'] = 'require'
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('POSTGRES_DB', 'evermind' if IS_PRODUCTION else 'mediacompile'),
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
            'HOST': os.environ.get('POSTGRES_HOST', '127.0.0.1'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '600' if IS_PRODUCTION else '0')),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'sslmode': 'require'
            } if IS_PRODUCTION else {},
        }
    }

# Custom User Model - Defined BEFORE initial migrations
AUTH_USER_MODEL = 'users.User'

# Password validation and hashing
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.AuthJsBridgeAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '300/minute',
        'ingestion': '120/minute',
        'search': '180/minute',
        'chat': '60/minute',
        'export_import': '20/minute',
        'auth': '30/minute',
    },
}

# CORS Configuration
cors_origins_env = os.environ.get('CORS_ALLOWED_ORIGINS')
if cors_origins_env:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in cors_origins_env.split(',') if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ]
CORS_ALLOW_CREDENTIALS = True

# Security Hardening & Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    if os.environ.get('SECURE_SSL_REDIRECT', 'false').lower() in ('true', '1'):
        SECURE_SSL_REDIRECT = True

# Auth.js Identity Bridge Secrets
INTERNAL_API_SECRET = os.environ.get(
    'INTERNAL_API_SECRET',
    'development-internal-api-secret-key-must-be-min-32-chars'
)
INTERNAL_API_ISSUER = os.environ.get('INTERNAL_API_ISSUER', 'evermind-web')
INTERNAL_API_AUDIENCE = os.environ.get('INTERNAL_API_AUDIENCE', 'evermind-api')

# Redis / Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0'),
    }
}

# Celery Configuration (runs directly on Windows host with -P solo)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes maximum for ingestion tasks

# Storage Provider Configuration (AWS S3 vs MinIO)
STORAGE_PROVIDER = os.environ.get(
    'STORAGE_PROVIDER',
    's3' if (IS_PRODUCTION or os.environ.get('AWS_STORAGE_BUCKET_NAME')) else 'minio'
).lower()

# AWS S3 Settings (Production default)
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'evermind2026')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'ap-south-1')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '').strip()
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '').strip()
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', None)

# MinIO S3 Object Storage Configuration (Development default)
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', '127.0.0.1:9000')
MINIO_ROOT_USER = os.environ.get('MINIO_ROOT_USER', 'minioadmin')
MINIO_ROOT_PASSWORD = os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin')
MINIO_BUCKET_NAME = os.environ.get('MINIO_BUCKET_NAME', 'mediacompile-uploads')
MINIO_USE_SSL = os.environ.get('MINIO_USE_SSL', 'false').lower() == 'true'

# LLM / Chatbot Configuration (Groq GPT-OSS 120B as Single Provider)
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'groq').lower()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'openai/gpt-oss-120b')
GROQ_BASE_URL = os.environ.get('GROQ_BASE_URL', 'https://api.groq.com')
GROQ_TIMEOUT_SECONDS = int(os.environ.get('GROQ_TIMEOUT_SECONDS', '45'))
GROQ_MAX_RETRIES = int(os.environ.get('GROQ_MAX_RETRIES', '3'))

# Web Search Configuration
WEB_SEARCH_ENABLED = os.environ.get('WEB_SEARCH_ENABLED', 'true').lower() in ('true', '1', 'yes')


# Vector Embeddings Configuration
# sentence-transformers/all-MiniLM-L6-v2 with exactly 384 dimensions for pgvector
EMBEDDING_PROVIDER = os.environ.get('EMBEDDING_PROVIDER', 'local').lower()
raw_model = os.environ.get('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
if raw_model in ('text-embedding-3-small', 'sentence-transformers/all-MiniLM-L6-v2') or 'all-minilm-l6-v2' in raw_model.lower():
    EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
    EMBEDDING_DIMENSIONS = 384
else:
    EMBEDDING_MODEL = raw_model
    EMBEDDING_DIMENSIONS = int(os.environ.get('EMBEDDING_DIMENSIONS', os.environ.get('EMBEDDING_DIMENSION', '384')))
    if EMBEDDING_DIMENSIONS == 1536:
        EMBEDDING_DIMENSIONS = 384
EMBEDDING_DIMENSION = EMBEDDING_DIMENSIONS
 
# Run Centralized Environment Validation
validate_environment_configuration()


