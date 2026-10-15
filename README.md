# Web Semantic — Éducation et formation

Socle de développement pour un projet individuel de Web sémantique : application Django avec rendu serveur, CSS classique, PostgreSQL et Apache Jena Fuseki. Aucun service Node.js, Tailwind ou stockage objet n'est nécessaire.

## Démarrer

Prérequis : un moteur Docker démarré (Docker Desktop ou OrbStack), Docker Compose et les ports configurés dans `.env` disponibles. Les bibliothèques Python et Java sont installées dans les images.

Le `.env` local est déjà créé avec une clé Django et un mot de passe PostgreSQL aléatoires. Il est exclu de Git et des images Docker. `.env.example` documente les variables sans contenir les secrets locaux.

```sh
docker compose up --build -d --wait
docker compose exec web python manage.py load_ontology
docker compose exec web python manage.py load_demo_data
```

- Application : <http://localhost:8000/>
- Backoffice métier : <http://localhost:8000/backoffice/>
- Connexion au backoffice : <http://localhost:8000/backoffice/connexion/>
- Administration Django : <http://localhost:8000/admin/>
- État de Django, PostgreSQL et Fuseki : <http://localhost:8000/health/>
- Endpoint SPARQL local : <http://localhost:3030/education/query>
- PostgreSQL depuis un client local : hôte `localhost`, port `5432`, identifiants du `.env`.

Un compte administrateur local `admin` est déjà créé dans la base de développement actuelle. Son mot de passe généré est conservé uniquement dans le `.env` local, sous `DJANGO_SUPERUSER_PASSWORD`. La base conserve le mot de passe haché. L'adresse `admin@localhost` sert de valeur locale ; aucun service d'envoi d'e-mails n'est configuré.

Sur une nouvelle base, générer les secrets puis créer le compte explicitement :

```sh
docker compose run --rm --no-deps web python manage.py createsuperuser --noinput
```

Cette commande charge les variables `DJANGO_SUPERUSER_*` du `.env`. Elle ne doit être lancée qu'une fois pour un même identifiant. Pour créer un autre compte de façon interactive : `docker compose exec web python manage.py createsuperuser`. Modifier le mot de passe dans `.env` ne change pas celui d'un compte existant ; utiliser `docker compose exec web python manage.py changepassword admin` pour le modifier en base.

Les migrations sont exécutées automatiquement au démarrage du serveur Django. Le dataset Fuseki `education` est créé automatiquement. L'import de l'ontologie reste une commande explicite : un redémarrage ne remplace pas les données sémantiques.

Cette distribution de Fuseki est le serveur officiel « plain » sans interface graphique. L'URL racine peut renvoyer 404 ; les endpoints SPARQL et Graph Store sont disponibles.

## Configuration

Toutes les variables d'environnement du projet sont centralisées dans `.env`. Compose les utilise pour configurer les conteneurs ; Django lit également ce fichier pour un éventuel lancement local. Les adresses internes utilisent les noms des services : `db:5432` et `fuseki:3030`. `POSTGRES_PORT` et `FUSEKI_PORT` concernent les ports publiés sur la machine, pas les communications internes.

Si vous changez `WEB_PORT`, adaptez aussi `DJANGO_CSRF_TRUSTED_ORIGINS`. Si vous changez `SEMANTIC_NAMESPACE`, adaptez les URI dans l'ontologie et les requêtes fournies. Les secrets sont obligatoires ; ne pas conserver les valeurs de remplacement de `.env.example`.

Pour recréer un `.env` après avoir récupéré le projet :

```sh
cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets

env_file = Path('.env')
content = env_file.read_text()
content = content.replace('replace-with-a-random-secret-key', secrets.token_urlsafe(64))
content = content.replace('replace-with-a-random-database-password', secrets.token_urlsafe(32))
content = content.replace('replace-with-a-random-admin-password', secrets.token_urlsafe(24))
env_file.write_text(content)
env_file.chmod(0o600)
PY
```

Les variables d'API d'IA seront ajoutées lorsque le fournisseur sera choisi et que la recherche en langage naturel sera implémentée. Aucune clé d'IA n'est requise pour démarrer ce socle.

## Répartition des données

| Composant | Contenu |
| --- | --- |
| PostgreSQL | Comptes administrateurs, permissions, sessions et tables techniques Django. |
| Fuseki / TDB2 | Ontologie OWL, catalogue de démonstration et, après raisonnement, inférences. |
| Stockage local Django | Futurs fichiers PDF et images, via `FileSystemStorage`, conservés dans le volume `media_data`. |

Les cours et leurs relations n'ont pas de copie SQL. Le backend sémantique se trouve dans `apps/semantic/services.py`. Il interroge Fuseki avec SPARQL et importe des graphes via le protocole Graph Store.

Les volumes `postgres_data`, `fuseki_data` et `media_data` conservent les données après un arrêt ou une reconstruction. Le volume `static_data` est réservé à la collecte des fichiers statiques. Le code et le CSS sont montés depuis le dossier du projet pour le développement.

## Ontologie et vérification SPARQL

`ontology/education.ttl` définit neuf classes, les relations et leurs inverses, les catégories disjointes, les niveaux et une chaîne de propriétés pour déduire les compétences développées par un parcours. `ontology/shapes.ttl` définit les contrôles de qualité des données. `ontology/demo.ttl` fournit huit cours fictifs, neuf compétences, neuf supports externes et trois parcours.

```sh
docker compose exec web python manage.py load_ontology
curl --fail --get \
  --data-urlencode query@ontology/queries/check_ontology.rq \
  --header 'Accept: application/sparql-results+json' \
  http://localhost:3030/education/query
```

L'import de l'ontologie remplace uniquement son graphe nommé. Le catalogue est ajouté dans un graphe distinct sans effacer les données existantes. Les inférences utilisent un troisième graphe. Les formulaires du backoffice mettent à jour les faits et les inférences ensemble ; les commandes d'import de schéma/exemples invalident les déductions et nécessitent un recalcul. Les requêtes précisent les graphes à consulter.

La syntaxe RDF est vérifiée avec RDFLib, les données avec SHACL, et la logique OWL avec un outil HermiT ponctuel. Fuseki n'exécute pas automatiquement ce raisonnement. Pour lancer le cycle complet :

```sh
docker compose exec web python manage.py prepare_ontology --from-fuseki
docker compose --profile tools run --rm reasoner
docker compose exec web python manage.py load_inferences
docker compose exec web python manage.py check_semantic_queries --with-inferences
```

Le profil `tools` ne démarre aucun service supplémentaire lors d'un `docker compose up` habituel. Le [guide de l'ontologie](ontology/README.md) explique le modèle, les contraintes et son examen dans Protégé.

## Commandes utiles

```sh
docker compose ps
docker compose logs -f web
docker compose exec web python manage.py check
docker compose exec web python manage.py test
docker compose exec web python manage.py shell
docker compose stop
docker compose start
docker compose down
```

`docker compose down` conserve les volumes. `docker compose down -v` les supprime avec toutes leurs données. Modifier le mot de passe dans `.env` ne modifie pas le mot de passe d'un rôle PostgreSQL déjà créé : il faut aussi le changer dans la base existante.

## Périmètre actuel

Le backoffice métier est fonctionnel : connexion réservée aux administrateurs actifs (`is_staff`), tableau de bord, listes filtrables/paginées, fiches détaillées, création, modification et suppression des cours, compétences, ressources et parcours. Les données sont lues et écrites dans Fuseki avec SPARQL ; aucune copie SQL du catalogue n'est créée.

Les PDF peuvent être téléversés, consultés dans une visionneuse et téléchargés. Leur contenu est conservé via le stockage local Django dans `media_data`. Le type, la signature PDF et la limite `PDF_UPLOAD_MAX_MB` sont contrôlés ; les liens web utilisent HTTP/HTTPS. Les métadonnées du fichier sont dans le graphe RDF. Le remplacement ou la suppression d'un support nettoie son ancien fichier lorsqu'il n'est plus utilisé.

Les mutations valident le catalogue avec SHACL, puis calculent en mémoire les déductions utiles via OWL-RL (sous-classes, relations inverses et chaîne parcours/cours/compétence). Les changements des faits et des inférences sont envoyés dans une seule requête SPARQL Update. HermiT reste disponible pour la vérification complète du modèle OWL ; il n'est pas lancé en Java à chaque formulaire.

Les cours utilisés comme prérequis et les compétences encore référencées sont protégés contre la suppression. Les parcours doivent conserver au moins un cours. Un verrou transactionnel PostgreSQL sérialise les mutations Django ; une empreinte du catalogue empêche l'enregistrement d'un formulaire devenu obsolète. Les modifications manuelles de Fuseki ou par les outils CLI ne passent pas par ce verrou et doivent être faites hors des écritures du backoffice.

Le projet individuel charge et valide le catalogue entier en mémoire à chaque mutation. Ce choix convient au petit volume prévu ; un catalogue volumineux nécessiterait des lectures ciblées et un raisonnement incrémental. Un incident réseau dont le résultat d'écriture est incertain peut laisser un fichier téléversé non référencé : il est conservé pour éviter de casser une écriture qui aurait abouti.

Le Django Admin natif, harmonisé avec le thème, gère les comptes et permissions. L'espace public conserve pour l'instant sa page d'accueil ; son catalogue et sa recherche en langage naturel via API d'IA seront développés dans la prochaine phase.

## Organisation du backoffice

- `apps/backoffice/` : authentification, formulaires, vues, routes et tests.
- `apps/semantic/catalogue.py` : modèle de lecture RDF, règles métier, mutations et déductions automatiques.
- `apps/semantic/services.py` : client HTTP de Fuseki, SPARQL Query/Update et Graph Store.
- `templates/backoffice/` : interface SSR commune et écrans de gestion.
- `static/css/backoffice.css`, `static/js/backoffice.js` : thème, navigation mobile, sélections filtrables et interactions des formulaires.

Les fichiers `ontology/generated/` ne sont pas créés ou modifiés par les formulaires. Les cours réels et leurs relations sont persistés directement dans Fuseki.

Ce Compose est destiné au développement local : `runserver` et la distribution des fichiers statiques/médias par Django utilisent `DJANGO_DEBUG=true`. Pour un déploiement public, il faudra préparer la configuration serveur et les accès aux services.

## Sources techniques

- [Django 5.2 LTS](https://docs.djangoproject.com/en/5.2/)
- [Django et PostgreSQL](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes)
- [Stockage des fichiers Django](https://docs.djangoproject.com/en/5.2/topics/files/)
- [Serveur Fuseki Plain](https://jena.apache.org/documentation/fuseki2/fuseki-plain)
- [Docker et Fuseki](https://jena.apache.org/documentation/fuseki2/fuseki-docker.html)

