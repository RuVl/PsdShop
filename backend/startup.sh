#!/bin/bash

# collect static files
uv run python manage.py collectstatic --no-input

# compile the .po catalogues (.mo files are build output, not tracked)
uv run python manage.py compilemessages --ignore=.venv

# Cron jobs run with a stripped environment, so nothing compose passes through `env_file` is
# visible to them - and settings.py reads os.environ alone, so every cron run would die at import
# on the first missing variable. Persist the environment and let each crontab line source it, the
# same way postgres/entrypoint.sh feeds backup.sh. Everything is dumped rather than a named list:
# a new setting must not silently break the broadcast sender months later.
CRON_ENV_FILE=/etc/psdshop-cron.env
: >"$CRON_ENV_FILE"
chmod 600 "$CRON_ENV_FILE"
for var in $(compgen -e); do
  printf 'export %s=%q\n' "$var" "${!var-}" >>"$CRON_ENV_FILE"
done

# run cron tasks
service cron start

# execute command from args
exec "$@"
