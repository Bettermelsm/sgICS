#!/bin/sh
# 容器启动入口：先迁移数据库，再按需创建 admin，最后启动服务
set -e

python manage.py migrate --noinput

# 通过环境变量非交互创建管理员（compose 文件里已预置 demo 账号）
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --noinput \
    --username "$DJANGO_SUPERUSER_USERNAME" \
    --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" || true
fi

exec "$@"
