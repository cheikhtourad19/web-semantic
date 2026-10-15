"""Vérifications ciblées des frontières de l'atelier public, sans écriture."""
from django.test import SimpleTestCase
from rdflib import Dataset, Literal, URIRef

from apps.semantic.validation import graph_uri
from .sparql import QueryError, prepare_query


class PublicQueryBoundaryTests(SimpleTestCase):
    def test_updates_and_non_table_queries_are_rejected(self):
        for query in ("DROP ALL", "INSERT DATA { <urn:s> <urn:p> <urn:o> }", "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"):
            with self.subTest(query=query), self.assertRaises(QueryError):
                prepare_query(query)

    def test_remote_access_and_extension_functions_are_rejected(self):
        for query in (
            "SELECT * WHERE { SERVICE <http://example.org/sparql> { ?s ?p ?o } }",
            "SELECT * FROM <http://example.org/data> WHERE { ?s ?p ?o }",
            "SELECT (<http://example.org/function>() AS ?value) WHERE {}",
        ):
            with self.subTest(query=query), self.assertRaises(QueryError):
                prepare_query(query)

    def test_local_from_prefixes_order_and_user_limit_are_preserved(self):
        dataset = Dataset()
        graph = dataset.graph(URIRef(graph_uri("catalogue")))
        for index in range(205):
            graph.add((URIRef(f"urn:course:{index}"), URIRef("urn:title"), Literal(index)))
        query = f"PREFIX select: <urn:>\nSELECT ?title FROM <{graph_uri('catalogue')}> WHERE {{ ?s select:title ?title }} ORDER BY ?title LIMIT 3"
        prepared, kind = prepare_query(query)
        self.assertEqual(kind, "SelectQuery")
        self.assertEqual([int(row.title) for row in dataset.query(prepared)], [0, 1, 2])
        unbounded, _ = prepare_query(f"SELECT ?s WHERE {{ GRAPH <{graph_uri('catalogue')}> {{ ?s ?p ?o }} }}")
        self.assertEqual(len(list(dataset.query(unbounded))), 201)

    def test_ask_is_supported_and_unknown_prefix_has_a_useful_error(self):
        query, kind = prepare_query("ASK {}")
        self.assertEqual(kind, "AskQuery")
        self.assertTrue(bool(Dataset().query(query)))
        with self.assertRaises(QueryError):
            prepare_query("SELECT * WHERE { ?s unknown:property ?o }")
