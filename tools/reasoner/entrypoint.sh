#!/bin/sh
set -eu

if [ ! -f /workspace/ontology/generated/education-demo.owl ]; then
    echo "Exécuter d'abord : docker compose exec web python manage.py prepare_ontology --from-fuseki" >&2
    exit 1
fi

rm -f /workspace/ontology/generated/reasoner-success.json
exec mvn --batch-mode --quiet -f /workspace/tools/reasoner/pom.xml compile exec:java \
    "-Dexec.args=/workspace/ontology/generated/education-demo.owl /workspace/ontology/generated/inferred.owl ${SEMANTIC_NAMESPACE}"

