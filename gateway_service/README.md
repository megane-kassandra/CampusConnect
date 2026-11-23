# API Gateway (`api-gateway`) — CampusConnect

Point d'entrée HTTP unique (Spring Cloud Gateway WebFlux) pour tous les clients
et le frontend de CampusConnect. Elle récupère sa configuration auprès du Config
Server, s'enregistre dans Eureka et route dynamiquement les requêtes vers les
microservices enregistrés via load-balancing (`lb://`).

## 1. Rôle dans l'architecture

    Clients / Frontend  ──►  API Gateway :8080  ──(lb://)──►  Microservices (AUTH-SERVICE, STUDENT-SERVICE)
                                │         │
                                │         └──(discovery)───►  Eureka Server :8762
                                └────(HTTP Basic)──────────►  Config Server :8888

Les clients **n'appellent jamais** les microservices directement par leur IP ou
leur port. Ils passent uniquement par **http://localhost:8080** : la Gateway
résout l'instance disponible via Eureka et applique les filtres de routage.

## 2. Prérequis et ordre de démarrage

Avant de lancer `gateway_service`, deux services doivent être opérationnels :
1. **Config Server (`:8888`)** — fournit `api-gateway.yml` et `application.yml`.
2. **Eureka Server (`:8762`)** — annuaire de découverte des services.

Démarrage de la Gateway :

    cd ~/Bureau/"TP INF4057"/CampusConnect
    set -a; source .env.config; set +a
    (cd gateway_service && nohup ./mvnw spring-boot:run > ../gateway-server.log 2>&1 &)

Le serveur écoute sur **http://localhost:8080** sous le nom applicatif `api-gateway`.

Preuve d'un démarrage sain dans `gateway-server.log` :

    Fetching config from server at : http://localhost:8888
    Located environment: name=api-gateway, profiles=[default]
    Netty started on port 8080 (http)
    DiscoveryClient_API-GATEWAY/...:api-gateway:8080: registering service...

## 3. Configuration (`api-gateway.yml`)

La configuration est centralisée dans `/home/christ/campusconnect-config-repo/api-gateway.yml` :

    server:
      port: 8080

    eureka:
      client:
        service-url:
          defaultZone: http://localhost:8762/eureka/
      instance:
        prefer-ip-address: true

    spring:
      cloud:
        gateway:
          server:
            webflux:
              routes:
                - id: auth-service
                  uri: lb://AUTH-SERVICE
                  predicates:
                    - Path=/api/auth/**
                  filters:
                    - StripPrefix=1
                - id: student-service
                  uri: lb://STUDENT-SERVICE
                  predicates:
                    - Path=/api/students/**
                  filters:
                    - StripPrefix=1

    management:
      endpoints:
        web:
          exposure:
            include: health,info,prometheus,env,refresh,gateway
      endpoint:
        gateway:
          access: read-only

Toute modification dans `api-gateway.yml` nécessite un `git commit` dans
`/home/christ/campusconnect-config-repo` puis un redémarrage de la Gateway
(ou un appel `POST /actuator/refresh`).

## 4. Table de routage

Le filtre `StripPrefix=1` retire le préfixe `/api` avant de transmettre la
requête au microservice cible :

| Route ID          | URL reçue par la Gateway (`:8080`) | Service Eureka cible   | URL reçue par le microservice |
|-------------------|------------------------------------|------------------------|-------------------------------|
| `auth-service`    | `/api/auth/**`                     | `lb://AUTH-SERVICE`    | `/auth/**`                    |
| `student-service` | `/api/students/**`                 | `lb://STUDENT-SERVICE` | `/students/**`                |

Exemple : `GET http://localhost:8080/api/auth/test` est redirigé vers
`GET http://<ip-auth>:<port-auth>/auth/test`.

## 5. Endpoints de contrôle (Actuator)

| Endpoint                       | Usage                                              |
|--------------------------------|----------------------------------------------------|
| `GET /actuator/health`         | État de santé de la Gateway (`UP` / `DOWN`)        |
| `GET /actuator/gateway/routes` | Liste JSON des routes actives, prédicats et filtres |
| `GET /actuator/env`            | Propriétés chargées (vérification Config Server)   |
| `POST /actuator/refresh`       | Recharge la configuration sans redémarrer          |

## 6. Vérifications rapides

    source .env.config

    # Config servie par le Config Server (:8888)
    curl -s -u "config-client:$CONFIG_CLIENT_PASSWORD" \
         http://localhost:8888/api-gateway/default | jq '{name, propertySources: [.propertySources[].name]}'

    # Santé de la Gateway (:8080)
    curl -s http://localhost:8080/actuator/health | jq .

    # Enregistrement UP dans Eureka (:8762)
    curl -s -H "Accept: application/json" http://localhost:8762/eureka/apps \
      | jq -r '.applications.application[]? | "\(.name) -> \(.instance[].status) (\(.instance[].ipAddr):\(.instance[].port."$"))"'

    # Routes chargées
    curl -s http://localhost:8080/actuator/gateway/routes | jq -r '.[].route_id'

## 7. Dépannage

| Symptôme                                  | Cause probable                                              | Solution                                                            |
|-------------------------------------------|-------------------------------------------------------------|---------------------------------------------------------------------|
| `503 Service Unavailable` sur `/api/<srv>`| Microservice cible non démarré ou absent d'Eureka (`:8762`) | Vérifier `/eureka/apps` et attendre 15-30 s (cache LoadBalancer)  |
| `404 Not Found`                           | Préfixe d'URL incorrect ou `StripPrefix=1` mal aligné       | Vérifier le path exposé côté contrôleur du microservice           |
| `Connect to http://localhost:8761 failed` | `defaultZone` pointe sur `8761` au lieu de `8762`           | Corriger `defaultZone: http://localhost:8762/eureka/` et commiter |
| Échec au démarrage (Config Server)        | `CONFIG_CLIENT_PASSWORD` non exporté ou Config Server KO   | Lancer `source .env.config` et démarrer `config_service` en premier |
| Port `8080` déjà utilisé                  | Ancienne instance de `gateway_service` encore active        | Libérer le port : `fuser -k 8080/tcp`                               |

## 8. Variables d'environnement requises (`.env.config`)

| Variable                 | Rôle                                                    |
|--------------------------|---------------------------------------------------------|
| `CONFIG_CLIENT_PASSWORD` | Authentification HTTP Basic auprès du Config Server     |
