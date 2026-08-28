# Built from the repository root (see docker-compose.yaml): the image carries both presentations
# of the storefront, so the SPA is built here too - vite writes hashed assets into the backend
# static tree and the Django shell template (frontend/vite.config.js), collectstatic publishes
# them onto the static volume nginx serves.
FROM docker.io/library/node:22.12-alpine3.21 AS spa-build
LABEL authors="RuVl_13"

WORKDIR /frontend

COPY frontend/package.json ./
RUN npm install --verbose

COPY frontend/ ./
# One domain in production, so the API is same-origin.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
# vite writes to ../backend/storefront/... relative to /frontend (OUT_DIR in vite.config.js).
RUN npm run build


FROM docker.io/library/python:3.13-slim
LABEL authors="RuVl_13"

# uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Set enviroment variables
ENV TZ=Europe/Moscow
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install cron, and gettext for `compilemessages` (translated e-mail copy)
RUN apt-get update && apt-get -y install cron gettext && apt-get -y autoremove

# Create the cronjob's log file
RUN touch /var/log/cron.log

# Prepare project directory
WORKDIR /app

# Install dependencies from the lockfile (cached layer, no project code yet)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy project to directory
COPY backend/ .

# The vite build output: hashed SPA assets (picked up by collectstatic) and the shell template
# the storefront views render for people.
COPY --from=spa-build /backend/storefront/static/storefront/spa ./storefront/static/storefront/spa
COPY --from=spa-build /backend/storefront/templates/storefront/shell.html ./storefront/templates/storefront/shell.html

# Copy the cronjob, apply it
COPY backend/cronjob /etc/cron.d/expire-orders-cron
RUN crontab /etc/cron.d/expire-orders-cron

# Run gunicorn
RUN chmod +x ./startup.sh
ENTRYPOINT ["./startup.sh", "uv", "run", "gunicorn", "-c", "gunicorn.py", "backend.wsgi:application"]
