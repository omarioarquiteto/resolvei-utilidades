# Dedicated, read-only Vibe-Trading review API for Resolvei.
# The official HKUDS source is pinned to a verified upstream commit.
FROM python:3.11-slim AS builder

ARG VIBE_TRADING_REF=2ac20879389f0e0104b59ad2f2076db75cd41fb2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN git init /opt/vibe-trading \
    && cd /opt/vibe-trading \
    && git remote add origin https://github.com/HKUDS/Vibe-Trading.git \
    && git fetch --depth 1 origin "$VIBE_TRADING_REF" \
    && git checkout --detach FETCH_HEAD

WORKDIR /opt/vibe-trading

COPY integrations/vibe-trading/vibe_lucro_routes.py /tmp/vibe_lucro_routes.py
COPY integrations/vibe-trading/vibe_lucro_server.py /tmp/vibe_lucro_server.py
COPY integrations/vibe-trading/install_routes.py /tmp/install_routes.py

RUN python /tmp/install_routes.py /opt/vibe-trading /tmp/vibe_lucro_routes.py /tmp/vibe_lucro_server.py

# Install the upstream hash-pinned runtime. The public app below deliberately
# exposes no general Vibe-Trading sessions, AgentLoop, MCP, broker or shell API.
RUN pip install --no-cache-dir --require-hashes -r requirements-lock.txt \
    && pip install --no-cache-dir --require-hashes -r requirements-channels-lock.txt \
    && pip install --no-cache-dir --no-deps -e . \
    && rm -rf .git

FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libfontconfig1 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin vibe \
    && mkdir -p /home/vibe/.vibe-trading \
    && chown -R vibe:vibe /home/vibe

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/home/vibe \
    VIBE_TRADING_HOME=/home/vibe/.vibe-trading \
    VIBE_TRADING_ENABLE_SHELL_TOOLS=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder --chown=vibe:vibe /opt/venv /opt/venv
COPY --from=builder --chown=vibe:vibe /opt/vibe-trading /opt/vibe-trading

WORKDIR /opt/vibe-trading
USER vibe

EXPOSE 10000

CMD ["sh", "-c", "uvicorn vibe_lucro_server:app --host 0.0.0.0 --port ${PORT:-10000}"]
