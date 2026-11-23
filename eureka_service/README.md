# Eureka Service — CampusConnect

Registre de services pour tous les microservices du projet CampusConnect.
Chaque service s'y enregistre au démarrage et y cherche les autres par leur
nom (`STUDENT-SERVICE`, `AUTH-SERVICE`, …) sans connaître leurs adresses IP.

## 1. Rôle dans l'architecture

    [API Gateway :8080]  ──► cherche STUDENT-SERVICE, AUTH-SERVICE
            │
            ▼
    [Eureka Server :8761]  ◄── s'enregistrent ici
            ▲
            │
    [auth-service] [student-service] [course-service] …
            │
            ▼
    [Config Server :8888]  ◄── d'où vient la config d'Eureka

- **Config Server** = *où* chaque service lit sa configuration.
- **Eureka** = *où* chaque service est joignable (adresse + port + état).

## 2. Démarrage

Prérequis :
- Config Server sur 8888 (`./run-config-server.sh` à la racine du monorepo) ;
- `eureka-server.yml` commité dans `~/campusconnect-config-repo/`.

Dans un terminal dédié :

    cd ~/Bureau/"TP INF4057"/CampusConnect/eureka_service
    set -a; source ../.env.config; set +a
    mvn spring-boot:run 2>&1 | tee ../eureka-server.log

Preuve d'un démarrage sain dans `eureka-server.log` :

    Fetching config from server at : http://localhost:8888
    Located environment: name=eureka-server, profiles=[default], version=<sha>
    Tomcat initialized with port 8761 (http)
    Started EurekaServiceApplication in X.XXX seconds

Aucune ligne `Connexion refusée` ni `registration failed` ne doit apparaître.
La ligne `Located environment: name=eureka-server` prouve que la config vient
du dépôt Git, pas du `application.yml` local.

## 3. Configuration

### Locale (`src/main/resources/application.yml`)

Volontairement minimal : uniquement l'amorçage vers le Config Server. Toute la
config fonctionnelle vient du dépôt Git.

    spring:
      application:
        name: eureka-server
      config:
        import: "optional:configserver:${CONFIG_SERVER_URL:http://localhost:8888}"
      cloud:
        config:
          username: config-client
          password: ${CONFIG_CLIENT_PASSWORD}

- `optional:configserver:` — Eureka démarre même si le Config Server est
  momentanément indisponible. Mais il tombe alors sur le port par défaut de
  Spring Boot (8080), ce qui produit une boucle `Connexion refusée`. Donc
  **démarrer le Config Server d'abord**.
- `CONFIG_CLIENT_PASSWORD` est lu depuis `.env.config` (non commité).

### Distante (`~/campusconnect-config-repo/eureka-server.yml`)

Toute la config fonctionnelle d'Eureka :

    server:
      port: 8761

    eureka:
      instance:
        hostname: localhost
      client:
        register-with-eureka: false
        fetch-registry: false
        service-url:
          defaultZone: http://${eureka.instance.hostname}:${server.port}/eureka/
      server:
        enable-self-preservation: false
        eviction-interval-timer-in-ms: 5000

`register-with-eureka: false` et `fetch-registry: false` sont **obligatoires**
pour un serveur standalone : sans eux, Eureka tente de s'enregistrer lui-même
avant que son propre port ne soit ouvert → boucle `Connexion refusée`.

Le Config Server écrase le `application.yml` local. `server.port` ne doit
figurer **que** dans le dépôt, jamais en local.

## 4. Endpoints utiles

Le dashboard HTML est consultable dans un navigateur :

    http://localhost:8761/

Vérification en ligne de commande :

    # Dashboard (HTML)
    curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8761/

    # Liste des services enregistrés (XML)
    curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8761/eureka/apps

    # Noms des services enregistrés
    curl -sS http://localhost:8761/eureka/apps | grep -oE '<name>[^<]+</name>'

Au démarrage, la liste est vide (seul Eureka tourne). Elle se remplit quand les
services métier et la Gateway s'enregistrent.

Pas de `/actuator/health` : `spring-boot-starter-actuator` n'est pas dans le
`pom.xml`, c'est volontaire (Eureka n'en a pas besoin).

## 5. Dépannage

| Symptôme                                                        | Cause                                                  |
|-----------------------------------------------------------------|--------------------------------------------------------|
| `Could not resolve placeholder 'CONFIG_CLIENT_PASSWORD'`        | `.env.config` non chargé                               |
| `Tomcat initialized with port 8080`                             | Config Server down et pas de `server.port` local       |
| `Connexion refusée` en boucle                                   | `register-with-eureka: false` absent du `eureka-server.yml` |
| `/eureka/apps` renvoie une liste vide                           | aucun service client enregistré (normal au démarrage)  |
| `401` au démarrage d'Eureka                                     | `CONFIG_CLIENT_PASSWORD` incorrect                     |
| `Path component must not be a symbolic link`                    | le dépôt de config est un symlink                      |
| `Located environment` présent mais `port 8080`                  | `eureka-server.yml` pas commité, ou cache du Config Server |

## 6. Tests manuels (smoke test)

    ss -ltnp | grep 8761
    curl -sS -o /dev/null -w "/ → %{http_code}\n" http://localhost:8761/
    curl -sS -o /dev/null -w "/eureka/apps → %{http_code}\n" http://localhost:8761/eureka/apps

Attendu : une ligne `LISTEN ... *:8761`, puis `200` et `200`.

### Test de la centralisation

Prouve qu'Eureka prend sa config dans le dépôt Git :

    # 1) Modifier le port dans le dépôt
    sed -i 's/port: 8761/port: 8762/' ~/campusconnect-config-repo/eureka-server.yml
    cd ~/campusconnect-config-repo && git add . && git commit -m "test: port 8762"

    # 2) Redémarrer Eureka
    pkill -f 'eureka_service.*spring-boot:run'; sleep 3
    cd ~/Bureau/"TP INF4057"/CampusConnect/eureka_service
    set -a; source ../.env.config; set +a
    mvn spring-boot:run 2>&1 | tee ../eureka-server.log

    # 3) Vérifier (après ~20 s)
    ss -ltnp | grep 8762

    # 4) Revenir à 8761
    sed -i 's/port: 8762/port: 8761/' ~/campusconnect-config-repo/eureka-server.yml
    cd ~/campusconnect-config-repo && git add . && git commit -m "revert: port 8761"
    pkill -f 'eureka_service.*spring-boot:run'; sleep 3
    cd ~/Bureau/"TP INF4057"/CampusConnect/eureka_service
    set -a; source ../.env.config; set +a
    mvn spring-boot:run 2>&1 | tee ../eureka-server.log

Si Eureka écoute sur 8762 sans que son `application.yml` local ait été touché,
la centralisation est prouvée.

## 7. Vérifier ce que le Config Server sert

    source ~/Bureau/"TP INF4057"/CampusConnect/.env.config
    curl -u "config-client:$CONFIG_CLIENT_PASSWORD" \
         http://localhost:8888/eureka-server/default \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); print([s["name"] for s in d["propertySources"]])'

Attendu :

    ['file:///home/christ/campusconnect-config-repo/eureka-server.yml',
     'file:///home/christ/campusconnect-config-repo/application.yml']

Si seul `application.yml` apparaît, `eureka-server.yml` n'est pas commité (ou
le Config Server a un cache). Vérifier :

    cd ~/campusconnect-config-repo
    git log --oneline -3
    git status -sb
    ls -l eureka-server.yml

## 8. Variables d'environnement (`.env.config`, non commité)

| Variable                  | Rôle                                              |
|---------------------------|---------------------------------------------------|
| `CONFIG_CLIENT_PASSWORD`  | mot de passe `config-client` sur le Config Server |
| `CONFIG_SERVER_URL`       | URL du Config Server (défaut `http://localhost:8888`) |

Eureka lui-même n'a **pas d'authentification** (HTTP Basic non activé). En
production, on ajouterait `spring-boot-starter-security` + un `SecurityConfig`.
En TP, ce n'est pas nécessaire.
