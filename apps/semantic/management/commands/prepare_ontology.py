import json
import hashlib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rdflib import Graph

from apps.semantic.services import SemanticStore, SemanticStoreError
from apps.semantic.validation import CatalogueValidationError, fingerprint, graph_uri, validate_catalogue


class Command(BaseCommand):
    help = "Vérifie le catalogue avec SHACL et exporte un instantané OWL pour HermiT/Protégé."

    def add_arguments(self, parser):
        parser.add_argument("--from-fuseki", action="store_true", help="Utiliser le catalogue actuel au lieu du fichier de démonstration.")

    def handle(self, *args, **options):
        try:
            catalogue = (
                SemanticStore().get_graph(graph_uri("catalogue")) if options["from_fuseki"]
                else Graph().parse(settings.BASE_DIR / "ontology/demo.ttl")
            )
            if not len(catalogue):
                raise CommandError("Le catalogue est vide ; charger les exemples d'abord.")
            ontology = validate_catalogue(catalogue)
        except (CatalogueValidationError, SemanticStoreError) as exc:
            raise CommandError(str(exc)) from exc
        target = settings.BASE_DIR / "ontology/generated"
        target.mkdir(parents=True, exist_ok=True)
        # Supprimer la preuve précédente avant de préparer un nouvel instantané.
        (target / "reasoner-success.json").unlink(missing_ok=True)
        ontology.serialize(target / "education.owl", format="xml")
        (ontology + catalogue).serialize(target / "education-demo.owl", format="xml")
        (target / "snapshot.json").write_text(json.dumps({
            "ontology": fingerprint(ontology), "catalogue": fingerprint(catalogue),
            "input_sha256": hashlib.sha256((target / "education-demo.owl").read_bytes()).hexdigest(),
        }, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Syntaxe RDF et SHACL valides. Instantané exporté dans {target}."
        ))
        self.stdout.write("La cohérence OWL doit maintenant être vérifiée avec HermiT.")
