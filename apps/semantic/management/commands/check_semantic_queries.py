import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.semantic.services import SemanticStore, SemanticStoreError


class Command(BaseCommand):
    help = "Vérifie sur Fuseki les résultats attendus des requêtes du jeu de démonstration."

    def add_arguments(self, parser):
        parser.add_argument("--with-inferences", action="store_true")

    def handle(self, *args, **options):
        directory = settings.BASE_DIR / "ontology/queries"
        cases = json.loads((directory / "expected.json").read_text())
        count = 0
        for case in cases:
            if case.get("inferences") and not options["with_inferences"]:
                continue
            try:
                response = SemanticStore().query((directory / case["file"]).read_text())
                rows = response["results"]["bindings"]
                actual = {row[case["variable"]]["value"] for row in rows}
            except (SemanticStoreError, KeyError, TypeError) as exc:
                raise CommandError(f"Échec de la requête {case['file']} : {exc}") from exc
            expected = {settings.SEMANTIC_NAMESPACE + value for value in case["expected"]}
            if actual != expected or len(rows) != len(expected):
                raise CommandError(f"Résultat inattendu pour {case['file']} : {sorted(actual)}")
            count += 1
            self.stdout.write(f"OK {case['file']} : {len(rows)} résultat(s)")
        self.stdout.write(self.style.SUCCESS(f"{count} requêtes SPARQL vérifiées sur Fuseki."))
