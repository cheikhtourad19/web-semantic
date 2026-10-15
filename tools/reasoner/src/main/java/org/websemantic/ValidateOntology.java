package org.websemantic;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;

import org.semanticweb.HermiT.ReasonerFactory;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.formats.RDFXMLDocumentFormat;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.OWL2DLProfile;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

public final class ValidateOntology {
    private static String sha256(Path file) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private static void rejectContradiction(OWLOntology source, Set<OWLAxiom> extra) throws Exception {
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology invalid = manager.createOntology(source.getAxioms());
        manager.addAxioms(invalid, extra);
        OWLReasoner reasoner = new ReasonerFactory().createReasoner(invalid);
        try {
            require(!reasoner.isConsistent(), "Le contre-exemple aurait dû être incohérent.");
        } finally {
            reasoner.dispose();
        }
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 3, "Arguments : input.owl inferred.owl namespace");
        Path output = Path.of(args[1]);
        String namespace = args[2];
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology ontology = manager.loadOntologyFromOntologyDocument(Path.of(args[0]).toFile());
        var profile = new OWL2DLProfile().checkOntology(ontology);
        require(profile.isInProfile(), "Ontologie hors profil OWL 2 DL : " + profile);
        OWLDataFactory factory = manager.getOWLDataFactory();
        OWLReasoner reasoner = new ReasonerFactory().createReasoner(ontology);
        Set<OWLAxiom> inferred = new HashSet<>();
        try {
            require(reasoner.isConsistent(), "HermiT : l'ontologie est incohérente.");
            require(reasoner.getUnsatisfiableClasses().getEntitiesMinusBottom().isEmpty(),
                    "Certaines classes métier sont impossibles à instancier.");

            for (OWLNamedIndividual individual : ontology.getIndividualsInSignature()) {
                if (!individual.getIRI().toString().startsWith(namespace)) continue;
                for (OWLClass type : reasoner.getTypes(individual, false).getFlattened()) {
                    if (!type.getIRI().toString().startsWith(namespace)) continue;
                    OWLAxiom axiom = factory.getOWLClassAssertionAxiom(type, individual);
                    if (!ontology.containsAxiom(axiom)) inferred.add(axiom);
                }
                for (OWLObjectProperty property : ontology.getObjectPropertiesInSignature()) {
                    if (!property.getIRI().toString().startsWith(namespace)) continue;
                    for (OWLNamedIndividual value : reasoner.getObjectPropertyValues(individual, property).getFlattened()) {
                        OWLAxiom axiom = factory.getOWLObjectPropertyAssertionAxiom(property, individual, value);
                        if (!ontology.containsAxiom(axiom)) inferred.add(axiom);
                    }
                }
            }

            var parcours = factory.getOWLNamedIndividual(IRI.create(namespace + "parcours_semantique"));
            var rdf = factory.getOWLNamedIndividual(IRI.create(namespace + "competence_rdf"));
            var develops = factory.getOWLObjectProperty(IRI.create(namespace + "developpeCompetence"));
            if (ontology.containsIndividualInSignature(parcours.getIRI())) {
                require(reasoner.isEntailed(factory.getOWLObjectPropertyAssertionAxiom(develops, parcours, rdf)),
                        "La chaîne parcours → cours → compétence n'a pas produit l'inférence attendue.");
            }
            System.out.println("HermiT : OWL 2 DL valide, ontologie cohérente, aucune classe insatisfiable.");
        } finally {
            reasoner.dispose();
        }

        var impossible = factory.getOWLNamedIndividual(IRI.create(namespace + "contre_exemple"));
        rejectContradiction(ontology, Set.of(
                factory.getOWLClassAssertionAxiom(factory.getOWLClass(IRI.create(namespace + "Cours")), impossible),
                factory.getOWLClassAssertionAxiom(factory.getOWLClass(IRI.create(namespace + "Competence")), impossible)));
        var level = factory.getOWLObjectProperty(IRI.create(namespace + "aPourNiveau"));
        rejectContradiction(ontology, Set.of(
                factory.getOWLObjectPropertyAssertionAxiom(level, impossible,
                        factory.getOWLNamedIndividual(IRI.create(namespace + "Debutant"))),
                factory.getOWLObjectPropertyAssertionAxiom(level, impossible,
                        factory.getOWLNamedIndividual(IRI.create(namespace + "Avance")))));
        System.out.println("Contre-exemples rejetés : catégories incompatibles et deux niveaux distincts.");

        OWLOntology result = manager.createOntology(inferred);
        manager.saveOntology(result, new RDFXMLDocumentFormat(), IRI.create(output.toFile()));
        Files.writeString(output.resolveSibling("reasoner-success.json"),
                "{\"consistent\":true,\"negative_cases\":2,\"inferred_axioms\":" + inferred.size()
                + ",\"input_sha256\":\"" + sha256(Path.of(args[0]))
                + "\",\"output_sha256\":\"" + sha256(output) + "\"}\n");
        System.out.println(inferred.size() + " assertions déduites exportées dans " + output);
    }
}
