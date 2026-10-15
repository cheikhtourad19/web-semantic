import json
import hashlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from rdflib import Dataset, Graph, Namespace, RDF

from .validation import CatalogueValidationError, graph_uri, validate_catalogue

EDU = Namespace("https://example.org/education#")


class CatalogueTests(SimpleTestCase):
    def setUp(self):
        self.catalogue = Graph().parse(settings.BASE_DIR / "ontology/demo.ttl")

    def test_demo_conforms_including_resources_typed_only_as_subclasses(self):
        validate_catalogue(self.catalogue)

    def test_missing_required_title_is_rejected(self):
        self.catalogue.remove((EDU.cours_python, EDU.titre, None))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    def test_two_levels_are_rejected(self):
        self.catalogue.add((EDU.cours_python, EDU.aPourNiveau, EDU.Avance))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    def test_reference_to_an_undeclared_skill_is_rejected(self):
        self.catalogue.add((EDU.cours_python, EDU.enseigne, EDU.competence_inconnue))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    def test_long_prerequisite_cycle_is_rejected(self):
        self.catalogue.add((EDU.cours_algo, EDU.aPourPrerequisCours, EDU.cours_integration))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    def test_a_pdf_requires_an_access_url(self):
        self.catalogue.remove((EDU.ressource_owl_pdf, EDU.urlAcces, None))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    def test_incompatible_categories_are_rejected(self):
        self.catalogue.add((EDU.cours_python, RDF.type, EDU.Competence))
        self.catalogue.add((EDU.cours_python, EDU.libelle, next(self.catalogue.objects(EDU.competence_python, EDU.libelle))))
        with self.assertRaises(CatalogueValidationError):
            validate_catalogue(self.catalogue)

    @patch("apps.semantic.management.commands.load_demo_data.SemanticStore")
    def test_loading_demo_twice_does_not_write_or_invalidate_inferences(self, store_class):
        store = store_class.return_value
        store.get_graph.return_value = self.catalogue
        call_command("load_demo_data", stdout=StringIO())
        store.add_graph.assert_not_called()
        store.delete_graph.assert_not_called()

    @patch("apps.semantic.management.commands.load_demo_data.SemanticStore")
    def test_loading_demo_preserves_an_existing_course(self, store_class):
        store = store_class.return_value
        existing = Graph()
        for triple in self.catalogue.triples((EDU.cours_sql, None, None)):
            existing.add(triple)
        for triple in self.catalogue.triples((EDU.competence_sql, None, None)):
            existing.add(triple)
        for triple in self.catalogue.triples((EDU.ressource_sql, None, None)):
            existing.add(triple)
        store.get_graph.return_value = existing
        call_command("load_demo_data", stdout=StringIO())
        store.add_graph.assert_called_once()
        store.replace_graph.assert_not_called()

    def test_reference_queries_match_the_expected_business_answers(self):
        directory = settings.BASE_DIR / "ontology/queries"
        dataset = Dataset()
        catalogue_graph = dataset.graph(graph_uri("catalogue"))
        catalogue_graph += self.catalogue
        dataset.graph(graph_uri("ontology")).parse(settings.BASE_DIR / "ontology/education.ttl")
        for case in json.loads((directory / "expected.json").read_text()):
            if case.get("inferences"):
                continue
            with self.subTest(query=case["file"]):
                rows = list(dataset.query((directory / case["file"]).read_text()))
                actual = {str(row[case["variable"]]) for row in rows}
                self.assertEqual(actual, {str(EDU[value]) for value in case["expected"]})
                self.assertEqual(len(rows), len(case["expected"]))


class InferenceImportTests(SimpleTestCase):
    def make_snapshot(self, root):
        directory = root / "ontology/generated"
        directory.mkdir(parents=True)
        Graph().serialize(directory / "education-demo.owl", format="xml")
        Graph().serialize(directory / "inferred.owl", format="xml")
        input_hash = hashlib.sha256((directory / "education-demo.owl").read_bytes()).hexdigest()
        output_hash = hashlib.sha256((directory / "inferred.owl").read_bytes()).hexdigest()
        (directory / "snapshot.json").write_text(json.dumps({
            "ontology": "old-schema", "catalogue": "old-catalogue", "input_sha256": input_hash,
        }))
        (directory / "reasoner-success.json").write_text(json.dumps({
            "consistent": True, "input_sha256": input_hash, "output_sha256": output_hash,
        }))
        return directory

    @patch("apps.semantic.management.commands.load_inferences.SemanticStore")
    def test_changed_fuseki_data_prevents_importing_stale_inferences(self, store_class):
        store = store_class.return_value
        store.get_graph.return_value = Graph()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_snapshot(root)
            with override_settings(BASE_DIR=root):
                with self.assertRaisesMessage(CommandError, "Les données ont changé"):
                    call_command("load_inferences", stdout=StringIO())
        store.replace_graph.assert_not_called()

    @patch("apps.semantic.management.commands.load_inferences.SemanticStore")
    def test_changed_reasoner_input_prevents_import(self, store_class):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = self.make_snapshot(root)
            with (snapshot / "education-demo.owl").open("a") as file:
                file.write("\n<!-- modified after validation -->\n")
            with override_settings(BASE_DIR=root):
                with self.assertRaisesMessage(CommandError, "Les fichiers générés ont changé"):
                    call_command("load_inferences", stdout=StringIO())
        store_class.assert_not_called()
