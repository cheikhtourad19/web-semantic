from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rdflib import Graph
from rdflib.compare import isomorphic

from apps.semantic.services import SemanticStore, SemanticStoreError
from apps.semantic.validation import CatalogueValidationError, graph_uri, validate_catalogue


class Command(BaseCommand):
    help = "Ajoute les exemples au catalogue sans remplacer les données existantes."

    def handle(self, *args, **options):
        demo = Graph().parse(settings.BASE_DIR / "ontology/demo.ttl")
        store = SemanticStore()
        try:
            existing = store.get_graph(graph_uri("catalogue"))
            combined = existing + demo
            validate_catalogue(combined)
            if isomorphic(existing, combined):
                self.stdout.write("Les exemples sont déjà présents ; aucune modification.")
                return
            # Invalider les déductions avant toute modification des faits sources.
            store.delete_graph(graph_uri("inferences"))
            store.add_graph(graph_uri("catalogue"), demo)
        except (CatalogueValidationError, SemanticStoreError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Catalogue validé : exemples ajoutés, {len(combined)} triplets au total."
        ))
