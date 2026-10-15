#!/bin/sh
set -eu

case "${FUSEKI_DATASET:-}" in
    ''|*[!a-zA-Z0-9_-]*)
        echo "FUSEKI_DATASET doit contenir uniquement lettres, chiffres, _ ou -." >&2
        exit 1
        ;;
esac

exec java -jar /opt/fuseki/fuseki.jar \
    --tdb2 --loc=/fuseki/data --update "/${FUSEKI_DATASET}"

