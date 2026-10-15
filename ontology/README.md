# Modèle sémantique : éducation et formation

L'ontologie définit le vocabulaire et les règles du domaine. Le catalogue contient les cours, les compétences, les supports et les parcours concrets. Les inférences sont les faits calculés à partir de ces deux sources : par HermiT pour la vérification complète, ou automatiquement par OWL-RL lors des mutations du backoffice.

## Classes et règles retenues

| Classe | Rôle et règles de saisie |
| --- | --- |
| `Cours` | Titre et description non vides, langue, durée positive en minutes, exactement un niveau, au moins une compétence enseignée. |
| `Competence` | Libellé non vide. Une même compétence peut être enseignée ou exigée par plusieurs cours. |
| `Ressource` | Titre, langue et adresse d'accès. Un support peut être associé à plusieurs cours. |
| `ParcoursApprentissage` | Titre, description et au moins un cours. Un cours peut appartenir à plusieurs parcours. |
| `Niveau` | Vocabulaire limité à `Debutant`, `Intermediaire` et `Avance`. |

`DocumentPDF`, `PageWeb`, `Video` et `Exercice` sont des sous-classes de `Ressource`. Elles peuvent se recouper : un exercice peut aussi être un PDF. Les cinq grandes catégories sont disjointes : une même instance ne peut pas être à la fois un cours et une compétence, par exemple.

Les prérequis de cours sont facultatifs et multiples. Ils représentent les liens directs ; les liens indirects sont explorés avec le chemin SPARQL `aPourPrerequisCours+`. Un cours ne peut pas être son propre prérequis et les cycles, même longs, sont rejetés.

Le modèle n'impose pas d'ordre total entre les cours d'un parcours. L'ordre pédagogique repose sur les prérequis ; une propriété d'ordre pourra être ajoutée si un futur écran l'exige.

## Les fichiers

- `education.ttl` : classes, propriétés, relations inverses, restrictions OWL et niveaux.
- `shapes.ttl` : contraintes SHACL portant sur les valeurs réellement présentes dans le catalogue.
- `demo.ttl` : huit cours fictifs, neuf compétences, neuf ressources externes et trois parcours.
- `queries/*.rq` : questions métier traduites en SPARQL.
- `queries/expected.json` : résultats attendus pour les exemples, permettant une vérification automatique.
- `generated/` : exports RDF/XML et résultats de HermiT, générés localement et exclus de Git.

Les cours d'exemple ne représentent pas une offre de formation réelle. Les ressources externes sont des liens vers des documentations ; leurs fichiers ne sont pas copiés dans notre stockage local.

## OWL, SHACL et HermiT

OWL décrit les connaissances en monde ouvert : un fait absent peut être inconnu. Une restriction OWL « au moins une compétence » ne suffit donc pas à vérifier qu'un formulaire a effectivement fourni cette compétence.

SHACL vérifie les données présentes : champs requis, types de valeurs, références, niveau unique et absence de cycle. Les commandes d'import du catalogue et les formulaires du backoffice l'exécutent avant l'écriture.

HermiT vérifie la cohérence logique OWL et les classes impossibles, puis déduit des relations. Le petit outil Java est limité à cette tâche ; le backend de l'application reste en Python/Django. Il teste aussi deux contre-exemples : un individu de catégories incompatibles et un individu ayant deux niveaux distincts.

La cohérence ne prouve pas à elle seule que le modèle répond au besoin : les requêtes métier et leurs résultats attendus servent à le vérifier.

## Exécution reproductible

```sh
docker compose up --build -d --wait
docker compose exec web python manage.py load_ontology
docker compose exec web python manage.py load_demo_data
docker compose exec web python manage.py prepare_ontology --from-fuseki
docker compose --profile tools run --rm reasoner
docker compose exec web python manage.py load_inferences
docker compose exec web python manage.py check_semantic_queries --with-inferences
docker compose exec web python manage.py test
```

L'outil HermiT est un conteneur ponctuel du profil `tools`. Il n'est pas démarré avec les trois services habituels. Le premier lancement télécharge ses dépendances Maven dans un volume cache.

`load_demo_data` ajoute les triplets d'exemple sans remplacer le catalogue. Un deuxième lancement identique ne change rien. Si la fusion avec les données présentes viole les règles SHACL, l'import est refusé. Le chargeur n'est pas un outil de mise à jour : modifier un exemple déjà importé nécessite une modification explicite de ses valeurs en base.

Le chargement de l'ontologie ou de nouveaux exemples par les commandes CLI invalide le graphe d'inférences. Après ces imports, il faut refaire la préparation et le raisonnement. L'import des inférences vérifie que les graphes de Fuseki correspondent toujours à l'instantané validé. Les formulaires métier recalculent leurs déductions automatiquement, en mémoire, et les enregistrent avec les changements du catalogue ; ils ne produisent aucun fichier OWL.

Les déductions automatiques utilisent `owlrl` pour les règles du modèle actuellement exploitées : sous-classes de ressources, relations inverses et chaîne `contientCours / enseigne → developpeCompetence`. Ce calcul OWL-RL ne remplace pas la validation complète OWL 2 DL par HermiT lors d'une évolution du schéma. Un test vérifie les 57 assertions attendues sur le jeu de démonstration, identiques aux assertions calculées par HermiT.

Les résultats attendus des neuf requêtes correspondent au catalogue de démonstration. Si ce catalogue est enrichi ou modifié, les attentes doivent être adaptées, ou ces vérifications exécutées dans un dataset de test dédié.

## Examiner avec Protégé

1. Exécuter `prepare_ontology --from-fuseki`.
2. Ouvrir `generated/education-demo.owl` dans Protégé pour examiner le schéma et les individus ensemble ; `generated/education.owl` contient le schéma seul.
3. Choisir HermiT dans le menu **Reasoner**, puis démarrer le raisonnement.
4. Vérifier la cohérence et les classes inférées. `owl:Nothing` ne doit contenir aucune classe métier.
5. Examiner `parcours_semantique` : les compétences RDF, OWL et SPARQL sont déduites via les cours qu'il contient.

Cette vérification interactive est distincte de l'exécution automatisée de HermiT. Elle permet de présenter et d'expliquer le modèle lors du suivi.

## Graphes dans Fuseki

| Graphe nommé | Contenu |
| --- | --- |
| `https://example.org/education/graphs/ontology` | Schéma OWL et niveaux de référence. |
| `https://example.org/education/graphs/catalogue` | Cours, compétences, ressources et parcours. |
| `https://example.org/education/graphs/inferences` | Assertions supplémentaires calculées par HermiT ou automatiquement par le backend OWL-RL. |

Le graphe par défaut n'est pas utilisé. Les requêtes nomment explicitement les graphes nécessaires. Les relations déduites ne sont pas recopiées dans le catalogue.

Exemples de déductions : `parcours_semantique developpeCompetence competence_rdf`, `competence_python estEnseigneePar cours_python` et `ressource_owl_pdf rdf:type Ressource`.

## Références

- [OWL 2 Primer — W3C](https://www.w3.org/TR/owl-primer/)
- [SHACL — W3C](https://www.w3.org/TR/shacl/)
- [pySHACL](https://github.com/RDFLib/pySHACL)
- [HermiT](https://github.com/owlcs/hermit-reasoner)

