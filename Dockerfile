# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS game-build
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libstdc++6 libfontconfig1 libx11-6 libxcursor1 libxinerama1 \
    libxrandr2 libxi6 libgl1 libasound2 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY scripts/fetch_godot.py scripts/fetch_godot.py
RUN python scripts/fetch_godot.py /opt/godot
RUN pip install --no-cache-dir Brotli==1.1.0
COPY game game
COPY scripts/build_web.sh scripts/compress_web.py scripts/
RUN GODOT_BIN=/opt/godot/godot bash scripts/build_web.sh

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY race race
COPY examples examples
COPY --from=game-build /build/web web
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY game/LICENSE.upstream.md ./GODOT_ASSETS_LICENSE.md
COPY game/Godot-COPYRIGHT.txt ./GODOT_COPYRIGHT.txt
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["python", "-m", "race", "--host", "0.0.0.0", "--port", "8080"]
