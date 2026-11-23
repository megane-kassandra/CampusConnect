# Config Server — CampusConnect

Serveur de configuration centralisé pour tous les microservices du projet
CampusConnect. Il lit un dépôt Git et sert à chaque service son YAML fusionné
via HTTP, avec authentification HTTP Basic.

## 1. Rôle dans l'architecture

    Dépôt Git local  ←(pull)←  Config Server :8888  ←(HTTP Basic)←  Microservices
                                                                ←(HTTP)←  Auth (Django)

Les services **ne lisent jamais** le dépôt Git. Ils interrogent le Config
Server. Seul le Config Server connaît le dépôt, la branche et les identifiants.

## 2. Démarrage

    cd ~/Bureau/"TP INF4057"/CampusConnect
    ./run-config-server.sh

Le script :
- charge `.env.config` (ENCRYPT_KEY, CONFIG_CLIENT_PASSWORD, CONFIG_ADMIN_PASSWORD) ;
- exporte CONFIG_BACKEND=git et CONFIG_GIT_URI=file:///home/christ/campusconnect-config-repo ;
- lance mvn spring-boot:run dans `config_service/`.

Le serveur écoute sur **http://localhost:8888** en profil `git`.

Preuve d'un démarrage sain dans `config-server.log` :

    The following 1 profile is active: "git"
    Tomcat initialized with port 8888 (http)
    Global AuthenticationManager configured with ... userDetailsService
    Started ConfigServiceApplication

Aucune ligne `Using generated security password` ne doit apparaître.

## 3. Sécurité

Deux utilisateurs en mémoire, mots de passe lus depuis `.env.config` et
encodés en BCrypt au démarrage :

| Utilisateur     | Rôles          | Usage                                |
|-----------------|----------------|--------------------------------------|
| `config-client` | CLIENT         | Lecture de la config des services    |
| `config-admin`  | ADMIN + CLIENT | Chiffrement/déchiffrement, admin     |

Règles d'accès :

| Endpoint                                    | Rôle requis |
|---------------------------------------------|-------------|
| `/actuator/health`, `/actuator/info`        | public      |
| `/encrypt/**`, `/decrypt/**`, `/key`        | ADMIN       |
| Tout le reste (`/{app}/{profile}`)          | CLIENT      |

## 4. Dépôt de configuration

- Chemin : `/home/christ/campusconnect-config-repo` (**pas** un symlink, JGit
  refuse les liens symboliques).
- Branche : `main`.
- Ce doit être un vrai dépôt Git avec **au moins un commit**.

Le serveur clone/pull au démarrage (`clone-on-start: true`, `force-pull: true`).
Un `git commit` dans le dépôt est visible au prochain `GET`, **sans redémarrer
le serveur**.

## 5. Endpoints utiles

Toutes les requêtes authentifiées doivent envoyer les bons identifiants.
Dans un terminal :

    source .env.config
    curl -sS -u "config-client:${CONFIG_CLIENT_PASSWORD}" \
         http://localhost:8888/<app>/<profile>

Exemples :

    # Config fusionnée pour student-service en profil dev
    curl -u "config-client:$CONFIG_CLIENT_PASSWORD" \
         http://localhost:8888/student-service/dev

    # Rendu YAML brut
    curl -u "config-client:$CONFIG_CLIENT_PASSWORD" \
         http://localhost:8888/student-service-dev.yml

    # Chiffrement d'un secret (ADMIN)
    curl -u "config-admin:$CONFIG_ADMIN_PASSWORD" \
         -H 'Content-Type: text/plain' \
         -X POST --data 'mon-secret' \
         http://localhost:8888/encrypt

## 6. Dépannage

| Symptôme                                | Cause                                  |
|-----------------------------------------|----------------------------------------|
| `401` avec le bon mot de passe          | `source .env.config` oublié            |
| `403` sur `/encrypt` avec `config-client` | rôle CLIENT, pas ADMIN                |
| `500` avec `Path component must not be a symbolic link` | dépôt est un symlink |
| `500` avec `Cannot load environment`    | dépôt non commité ou branche absente   |
| `/actuator/health` = `DOWN`             | git repository inaccessible            |
| Modification non visible                | pas de `git commit` dans le dépôt      |

## 7. Tests manuels (smoke test)

    ./debug-config-server.sh > diagnostic.txt 2>&1

Le script teste : health, 401 sans auth, 401 mauvais mot de passe, 200 avec
`config-client` sur `student-service/dev`, 403 client sur `/encrypt`, 200
admin sur `/encrypt`.

## 8. Variables d'environnement (`.env.config`, non commité)

| Variable                | Rôle                                 |
|-------------------------|--------------------------------------|
| `ENCRYPT_KEY`           | clé symétrique `{cipher}`            |
| `CONFIG_CLIENT_PASSWORD`| mot de passe `config-client`         |
| `CONFIG_ADMIN_PASSWORD` | mot de passe `config-admin`          |
