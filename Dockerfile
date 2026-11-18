FROM caddy:2-alpine AS proxy

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY --from=proxy /usr/bin/caddy /usr/bin/caddy
COPY requirements.txt .
RUN python -m pip install -r requirements.txt \
    && useradd --system --create-home app

COPY app.py ui_helpers.py ui_theme.py ./
COPY .streamlit/config.toml .streamlit/config.toml
COPY backend/ backend/
COPY database/ database/
COPY deploy/ deploy/
COPY pages/ pages/
COPY sample_data/ sample_data/
COPY scripts/ scripts/
COPY services/ services/
COPY styles/ styles/

USER app
CMD ["python", "-m", "deploy.start"]
