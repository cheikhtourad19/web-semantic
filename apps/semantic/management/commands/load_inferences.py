import json
import hashlib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rdflib import Graph, RDF, URIRef

from apps.semantic.services import SemanticStore, SemanticStoreError
from apps.semantic.validation import fingerprint, graph_uri


class Command(BaseCommand):
    help = "Charge les inférences de HermiT si elles correspondent encore aux données de Fuseki."

    def handle(self, *args, **options):
        directory = settings.BASE_DIR / "ontology/generated"
        try:
            snapshot = json.loads((directory / "snapshot.json").read_text())
            proof = json.loads((directory / "reasoner-success.json").read_text())
            result = Graph().parse(directory / "inferred.owl")
        except (OSError, ValueError) as exc:
            raise CommandError("Exécuter prepare_ontology puis le raisonneur HermiT avant cet import.") from exc
        if proof.get("consistent") is not True:
            raise CommandError("La validation HermiT n'a pas réussi.")
        source_hash = hashlib.sha256((directory / "education-demo.owl").read_bytes()).hexdigest()
        result_hash = hashlib.sha256((directory / "inferred.owl").read_bytes()).hexdigest()
        if (source_hash != snapshot.get("input_sha256")
                or source_hash != proof.get("input_sha256")
                or result_hash != proof.get("output_sha256")):
            raise CommandError("Les fichiers générés ont changé ; refaire la préparation et HermiT.")
        store = SemanticStore()
        try:
            ontology = store.get_graph(graph_uri("ontology"))
            catalogue = store.get_graph(graph_uri("catalogue"))
            if fingerprint(ontology) != snapshot["ontology"] or fingerprint(catalogue) != snapshot["catalogue"]:
                raise CommandError("Les données ont changé. Refaire prepare_ontology --from-fuseki puis HermiT.")
            namespace = settings.SEMANTIC_NAMESPACE
            inferences = Graph()
            for subject, predicate, obj in result:
                if not isinstance(subject, URIRef) or not str(subject).startswith(namespace):
                    continue
                if str(predicate).startswith(namespace) or (predicate == RDF.type and str(obj).startswith(namespace)):
                    inferences.add((subject, predicate, obj))
            store.replace_graph(graph_uri("inferences"), inferences)
        except SemanticStoreError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{len(inferences)} triplets déduits chargés dans le graphe d'inférences."))
