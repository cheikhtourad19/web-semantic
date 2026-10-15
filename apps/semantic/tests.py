from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import httpx
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .services import SemanticStore, SemanticStoreError


class SemanticStoreTests(SimpleTestCase):
    @patch("apps.semantic.services.httpx.post", side_effect=httpx.ConnectError("offline"))
    def test_network_failure_has_a_consistent_application_error(self, post):
        with self.assertRaises(SemanticStoreError):
            SemanticStore().query("ASK {}")

    @patch("apps.semantic.services.httpx.post")
    def test_malformed_sparql_response_is_rejected(self, post):
        post.return_value.json.side_effect = ValueError("invalid JSON")
        with self.assertRaises(SemanticStoreError):
            SemanticStore().query("ASK {}")


class OntologyImportTests(SimpleTestCase):
    @patch("apps.semantic.management.commands.load_ontology.SemanticStore.delete_graph")
    @patch("apps.semantic.management.commands.load_ontology.SemanticStore.replace_graph")
    def test_only_the_dedicated_ontology_graph_is_replaced(self, replace_graph, delete_graph):
        call_command("load_ontology", stdout=StringIO())
        graph_uri, graph = replace_graph.call_args.args
        self.assertEqual(graph_uri, f"{settings.SEMANTIC_NAMESPACE.rstrip('#/')}/graphs/ontology")
        self.assertGreater(len(graph), 0)
        delete_graph.assert_called_once_with(f"{settings.SEMANTIC_NAMESPACE.rstrip('#/')}/graphs/inferences")

    @patch("apps.semantic.management.commands.load_ontology.SemanticStore.replace_graph")
    def test_invalid_rdf_is_rejected_before_contacting_fuseki(self, replace_graph):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.ttl"
            source.write_text("this is not valid turtle", encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("load_ontology", str(source), stdout=StringIO())
        replace_graph.assert_not_called()

