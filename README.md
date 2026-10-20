# UE-AD-A1-MIXTE

TP "API mixtes"  : une petite application de cinéma découpée en quatre services,
qui ne parlent pas tous le même langage. User et Schedule exposent une API REST, Movie et
Booking une API GraphQL. Les données sont dans MongoDB et l'authentification passe par des
tokens JWT.

## Les services

| Service  | API     | Port | Rôle |
|----------|---------|------|------|
| User     | REST    | 3004 | comptes, connexion, création des tokens JWT |
| Movie    | GraphQL | 3200 | films et acteurs |
| Schedule | REST    | 3003 | séances (un film à une date) |
| Booking  | GraphQL | 3002 | réservations des utilisateurs |

À côté, MongoDB tourne sur le port 27017 et mongo-express (une interface web pour voir la
base) sur http://localhost:8081.

Chaque service a sa doc dans son dossier : `user/user.yaml`, `movie/movie.yaml`,
`schedule/schedule.yaml` et `booking/booking.yaml` (OpenAPI), plus les schémas
`movie.graphql` et `booking.graphql`.

### Qui appelle qui

- Booking demande à Schedule si une séance existe et si elle est ouverte, à Movie le détail
  des films, et à User si le compte est toujours actif.
- Schedule vérifie auprès de Movie que le film existe avant de créer une séance.
- Quand un film est supprimé, Movie prévient Schedule, qui annule les séances du film.
  Schedule prévient à son tour Booking, qui annule les réservations de ces séances.
  De la même façon, supprimer un compte annule ses réservations.

Chaque appel transmet le token de l'utilisateur, donc les droits sont vérifiés partout.
Pour les annulations en cascade, si le service suivant ne répond pas, rien n'est modifié :
on reçoit une erreur (502 côté REST, une erreur GraphQL côté Movie) et on peut réessayer.

## Lancer le projet

Il faut Docker.

1. Créer le fichier `.env` à la racine en copiant `.env.example`, et y mettre ses propres
   mots de passe.

2. Générer la paire de clés pour les tokens (User signe avec la clé privée, les autres
   services vérifient avec la clé publique) :

   ```
   mkdir keys
   openssl genrsa -out keys/private_key.pem 2048
   openssl rsa -in keys/private_key.pem -pubout -out keys/public_key.pem
   ```

3. Tout démarrer :

   ```
   docker compose up -d --build
   ```

Au premier lancement, chaque service remplit sa collection MongoDB à partir de ses fichiers
JSON (`data/*.json`, ou `databases/users.json` pour User). Ensuite ces fichiers ne sont plus
lus.

Pour lancer un service sans Docker (pratique pour déboguer), on démarre seulement Mongo avec
`docker compose up -d mongo`, on installe les dépendances avec
`pip install -r requirements.txt`, puis on lance `python user.py` (ou `movie.py`...) dans le
dossier du service. Il lit la connexion à Mongo dans le `.env`.

## Se connecter

Tous les comptes de départ ont le mot de passe `root`. Par exemple :

- `chris@gmail.com` : ADMIN
- `peter@gmail.com` : USER

On récupère un token avec :

```
curl -X POST http://localhost:3004/login -H "Content-Type: application/json" \
     -d '{"email": "chris@gmail.com", "password": "root"}'
```

et on l'envoie ensuite dans le header `Authorization: Bearer <token>`. Le token dure 3 heures.

Pas besoin de compte pour consulter les films et les séances : Movie et Schedule acceptent
les lectures sans token, et un visiteur voit la même chose qu'un utilisateur connecté. Le
token devient obligatoire pour réserver, gérer son compte, ou modifier quoi que ce soit (admin).

Pour Movie et Booking, tout passe par `POST /graphql`, par exemple :

```
{ movie_with_title(_title: "Creed") { title rating actors { firstname lastname } } }
```

## Quelques choix

- Rien n'est vraiment supprimé de la base pour les comptes, les films et les séances : ils
  passent au statut `DELETED`. Un compte supprimé ne peut plus se connecter, et son token est refusé
  tout de suite par User. Un film supprimé n'est plus visible que par les admins.
- Une réservation ou une séance annulée passe au statut `CANCELED`. Une séance annulée ne
  peut pas être rouverte. Une séance supprimée n'est plus visible que par les admins, et
  libère son créneau : on peut reprogrammer le même film à la même date.
- Une séance créée est d'abord en `DRAFT` : seuls les admins la voient, jusqu'à ce qu'elle
  passe en `AVAILABLE`.
0

## Tester

Le dossier `postman/` contient une collection par service, avec des tests sur chaque
requête. Son README explique comment les importer et les lancer.


