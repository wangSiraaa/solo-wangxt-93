#!/usr/bin/env bash
# 一键启动演示：PostgreSQL -> 迁移 -> 灌演示数据 -> Django API -> React UI
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PG_PREFIX="${PG_PREFIX:-$HOME/pgenv}"
PGDATA="${PGDATA:-$HOME/pgdata}"
PGPORT="${PGPORT:-5432}"
PGHOST="${PGHOST:-/tmp}"
PGDATABASE="${PGDATABASE:-irv}"
# 演示密钥仅留在当前进程环境，不落盘、不提交；调用方可自行传入固定值。
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi

echo "[1/5] 检查/启动 PostgreSQL ($PG_PREFIX)"
if [ ! -x "$PG_PREFIX/bin/pg_ctl" ]; then
  echo "未找到 $PG_PREFIX 下的 PostgreSQL。可用 micromamba 安装："
  echo "  micromamba create -y -p $PG_PREFIX -c conda-forge postgresql=16"
  exit 1
fi
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  "$PG_PREFIX/bin/initdb" -D "$PGDATA" -U postgres --auth=trust --encoding=UTF8 --locale=C
fi
if ! "$PG_PREFIX/bin/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  "$PG_PREFIX/bin/pg_ctl" -D "$PGDATA" -l "$PGDATA/logfile" \
    -o "-p $PGPORT -k $PGHOST" start
  sleep 2
fi
if ! "$PG_PREFIX/bin/psql" -h "$PGHOST" -p "$PGPORT" -U postgres -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" | grep -q 1; then
  "$PG_PREFIX/bin/createdb" -h "$PGHOST" -p "$PGPORT" -U postgres "$PGDATABASE"
fi

echo "[2/5] Django 迁移"
cd "$ROOT/backend/irv_system"
export PGHOST PGPORT PGDATABASE PGUSER=postgres
python3 manage.py migrate --noinput

echo "[3/5] 灌演示数据（主选举草稿态、决胜局已发布锁定）"
python3 manage.py seed_demo --main-draft

echo "[4/5] 启动 Django REST API (127.0.0.1:8000)"
( python3 manage.py runserver 127.0.0.1:8000 >/tmp/irv-django.log 2>&1 & echo $! >/tmp/irv-django.pid )

echo "[5/5] 启动 React UI (127.0.0.1:5173)"
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
( npm run dev -- --host 127.0.0.1 >/tmp/irv-vite.log 2>&1 & echo $! >/tmp/irv-vite.pid )

cat <<EOF

==============================================================
  API:  http://127.0.0.1:8000/api/
  UI :  http://127.0.0.1:5173/
  规则: http://127.0.0.1:8000/api/rules/

  停止: kill \$(cat /tmp/irv-django.pid) \$(cat /tmp/irv-vite.pid)
        $PG_PREFIX/bin/pg_ctl -D $PGDATA stop
==============================================================
EOF
