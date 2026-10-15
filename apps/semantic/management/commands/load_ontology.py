from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rdflib import Graph

from apps.semantic.services import SemanticStore, SemanticStoreError


class Command(BaseCommand):
    help = "Charge une ontologie dans son graphe nomme dedie, sans effacer les instances."

    def add_arguments(self, parser):
        parser.add_argument(
            "source", nargs="?", default=str(settings.BASE_DIR / "ontology" / "education.ttl")
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.is_file():
            raise CommandError(f"Fichier introuvable : {source}")
        try:
            graph = Graph().parse(source)
        except Exception as exc:
            raise CommandError("Le fichier n'est pas un document RDF valide.") from exc
        expected_namespace = settings.SEMANTIC_NAMESPACE
        if not any(str(subject).startswith(expected_namespace) for subject in graph.subjects()):
            raise CommandError("Le namespace de l'ontologie ne correspond pas a SEMANTIC_NAMESPACE.")
        graph_uri = f"{expected_namespace.rstrip('#/')}/graphs/ontology"
        try:
            SemanticStore().delete_graph(f"{expected_namespace.rstrip('#/')}/graphs/inferences")
            SemanticStore().replace_graph(graph_uri, graph)
        except SemanticStoreError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Ontologie chargee : {len(graph)} triplets dans {graph_uri}"))

