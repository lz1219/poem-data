# 江山行止 · 文献（同源部署：前端 + API 同一进程）
#
# 构建（上下文 = server/）：
#   docker build -t poem-web .
#
# 运行（数据挂到 /srv）：
#   docker run -d --name poem-web --network host \
#     -e DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/jiangshan_web \
#     -e PUBLIC_DIR=/srv -e DATA_DIR=/srv/data \
#     -v /opt/poem-data:/srv:ro poem-web

FROM docker.1ms.run/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DEBUG=0 \
    DJANGO_SECRET=change-me-in-runtime \
    PUBLIC_DIR=/srv \
    DATA_DIR=/srv/data \
    PORT=8081

WORKDIR /app

COPY requirements.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

# 后台静态资源打进镜像，运行时由 whitenoise 直接发（生产不靠 runserver）
RUN python manage.py collectstatic --noinput

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.getenv('PORT','8081'),timeout=3)"

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py import_json --keep && gunicorn atlas.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 --access-logfile -"]
