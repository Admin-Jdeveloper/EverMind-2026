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
    from urllib.parse import urlparse, parse_qs, unquote
    parsed_db = urlparse(DATABASE_URL)
    db_port = str(parsed_db.port or 5432)
    db_host = parsed_db.hostname or ''
    is_pooler = 'pooler.supabase.com' in db_host or db_port in ('6543', '5432')
    is_transaction_pooler = db_port == '6543'

    # In pooled environments, default CONN_MAX_AGE to 0 so connections return to the pool immediately after each request.
    default_conn_max_age = '0' if (is_pooler or not IS_PRODUCTION) else '60'
    conn_max_age = int(os.environ.get('DB_CONN_MAX_AGE', default_conn_max_age))

    db_options = {
        'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
    }
    # Transaction Poolers (e.g. Supabase Supavisor on 6543, PgBouncer) require disabling prepared statements and server-side cursors
    if is_transaction_pooler:
        db_options['prepare_threshold'] = None

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(parsed_db.path.lstrip('/')),
            'USER': unquote(parsed_db.username or ''),
            'PASSWORD': unquote(parsed_db.password or ''),
            'HOST': db_host,
            'PORT': db_port,
            'CONN_MAX_AGE': conn_max_age,
            'CONN_HEALTH_CHECKS': True,
            'DISABLE_SERVER_SIDE_CURSORS': is_transaction_pooler,
            'OPTIONS': db_options,
        }
    }
    # Parse query parameters such as sslmode
    qs = parse_qs(parsed_db.query)
    if 'sslmode' in qs:
        DATABASES['default']['OPTIONS']['sslmode'] = qs['sslmode'][0]
    elif IS_PRODUCTION or 'supabase.com' in db_host:
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
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '0')),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': int(os.environ.get('DB_CONNECT_TIMEOUT', '10')),
                **({'sslmode': 'require'} if IS_PRODUCTION else {})
            },
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
        'core.throttling.SafeAnonRateThrottle',
        'core.throttling.SafeUserRateThrottle',
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

# Redis / Cache Configuration (connection capped for managed cloud Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0'),
        'TIMEOUT': int(os.environ.get('CACHE_DEFAULT_TIMEOUT', '300')),  # 5-minute bounded TTL prevents permanent key leak
        'OPTIONS': {
            'max_connections': 4,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'health_check_interval': 15,  # Active health check PINGs prevent idle disconnects
        }
    }
}

# Celery Configuration (runs directly on Windows host with -P solo or on Render worker)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')

# Resilient Kombu Redis Transport Options
# Fixes [WinError 10054] connection resets by sending TCP keepalive and periodic health check PINGs
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'health_check_interval': 15,          # Send PING every 15s to keep idle connections alive through NAT/firewalls
    'socket_timeout': 15.0,               # Bounded socket read/write timeout
    'socket_connect_timeout': 5.0,        # Bounded socket connect timeout
    'socket_keepalive': True,             # Enable TCP keepalive (SO_KEEPALIVE)
    'retry_on_timeout': True,             # Retry operations on socket timeout
    'visibility_timeout': 43200,          # 12-hour visibility timeout for large PDF / transcript ingestion
    'max_connections': 6,                 # Bounded connection pool per worker process
}

# Authoritative ingestion state is persisted in PostgreSQL ContentItem (STATUS_COMPLETED, etc.)
# Disable result backend by default to avoid retaining unneeded task results and tracebacks in Redis memory.
_raw_backend = os.environ.get('CELERY_RESULT_BACKEND', '')
if not _raw_backend or _raw_backend.lower() in ('none', 'false', '0'):
    CELERY_RESULT_BACKEND = None
else:
    if _raw_backend.endswith('/1') and any(cloud in _raw_backend for cloud in ('redis.io', 'upstash.io', 'supabase', 'rediss://')):
        CELERY_RESULT_BACKEND = _raw_backend[:-2] + '/0'
    else:
        CELERY_RESULT_BACKEND = _raw_backend

# If result backend is explicitly configured, enforce strict 5-minute expiration (default is 1 day / 86400s)
CELERY_RESULT_EXPIRES = int(os.environ.get('CELERY_RESULT_EXPIRES', '300'))
CELERY_TASK_IGNORE_RESULT = True  # State is persisted authoritatively in PostgreSQL ContentItem
CELERY_TASK_TRACK_STARTED = False # Avoid persistent Redis pubsub subscriber overhead
CELERY_WORKER_SEND_TASK_EVENTS = False # Avoid Kombu event queue accumulation in Redis
CELERY_TASK_SEND_SENT_EVENT = False
CELERY_EVENT_QUEUE_EXPIRES = 60 # Kombu event queues expire after 60s
CELERY_BROKER_POOL_LIMIT = 5
CELERY_REDIS_MAX_CONNECTIONS = 6
CELERY_RESULT_BACKEND_MAX_CONNECTIONS = 2

# Connection Reconnection & Resilience Settings
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 100  # Resilient exponential backoff

# Task Reliability & Idempotency Controls
CELERY_TASK_ACKS_LATE = True                     # Acknowledge only after task execution completes
CELERY_TASK_REJECT_ON_WORKER_LOST = True         # Requeue task if worker process dies unexpectedly
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = False  # Allow running task to finish during transient broker resets
CELERY_TASK_TIME_LIMIT = 600                     # 10 minutes hard execution limit
CELERY_TASK_SOFT_TIME_LIMIT = 540                # 9 minutes soft execution limit
CELERY_TASK_DEFAULT_QUEUE = 'celery'
CELERY_TASK_ROUTES = {
    'content.tasks.process_document_content': {'queue': 'celery'},
    'content.tasks.process_url_content': {'queue': 'celery'},
    'content.tasks.process_note_content': {'queue': 'celery'},
    'content.tasks.generate_chunk_embeddings': {'queue': 'celery'},
    'content.tasks.reembed_user_content': {'queue': 'celery'},
    'integrations.tasks.*': {'queue': 'celery'},
}
CELERY_IMPORTS = (
    'content.tasks',
    'integrations.tasks',
)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

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


