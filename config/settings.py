"""Django settings for sgICS (智能客服 demo)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'demo-secret-key-change-me')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    # core 排在 admin 之前，以便覆盖 admin 模板（如右上角版本号）
    'core',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
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
WSGI_APPLICATION = 'config.wsgi.application'

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
                'core.context_processors.version',
                'core.context_processors.workbench_guide',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Docker 交付时通过 DB_PATH 指向挂载卷，保持数据持久化
        'NAME': os.environ.get('DB_PATH', BASE_DIR / 'db.sqlite3'),
    }
}

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 上传文件（知识库文档等）：Docker 里通过环境变量指向 /data 卷
MEDIA_URL = 'media/'
MEDIA_ROOT = os.environ.get('MEDIA_PATH', BASE_DIR / 'media')

# ---- 客服 demo 业务配置 ----
CS_DEFAULT_REPLY = '您好，我是智能客服助手，您的问题已收到，稍后为您详细解答~'
CS_AI_FAIL_TRANSFER_THRESHOLD = 3  # AI 连续兜底失败 N 次后自动转人工
CS_CONTEXT_ROUNDS = 5  # 传给 LLM 的上下文轮数
