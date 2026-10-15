#!/bin/sh
set -eu

# Compose attend deja PostgreSQL et Fuseki avant de lancer Django.
# Les commandes ponctuelles (tests, shell...) n'executent pas les migrations.
if [ "${1:-}" = "python" ] && [ "${2:-}" = "manage.py" ] && [ "${3:-}" = "runserver" ]; then
    python manage.py migrate --noinput
fi

exec "$@"

