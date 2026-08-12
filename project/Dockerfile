# Two stages: build the React UI with Node, then run everything from Python.
# The Node toolchain never reaches the final image — only web/dist does.

FROM node:20-alpine AS web
WORKDIR /web

# Dependencies are copied first so an app-code change does not re-run npm ci.
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build


FROM python:3.12-slim AS runtime
WORKDIR /app

# git is a runtime dependency, not a build one: ingesting a repository URL
# shells out to `git clone`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# No NIGHTRAG_PORT here on purpose: platform-provided PORT (Render, Heroku,
# Fly) must win, and settings.py falls back to 8000 when nothing is set
# (which is what docker-compose maps).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NIGHTRAG_HOST=0.0.0.0 \
    NIGHTRAG_QDRANT_DIR=/data/qdrant

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY server/ ./server/
COPY main.py run_server.py ./
COPY --from=web /web/dist ./web/dist

# The embedded Qdrant store must outlive the container — mount a volume here.
VOLUME ["/data"]
EXPOSE 8000

# Ingesting a server-side path would read the container's filesystem, which is
# not what anyone means by it in a container. Git URLs and uploads still work.
ENV NIGHTRAG_ALLOW_LOCAL_PATH=0

CMD ["python", "run_server.py"]
