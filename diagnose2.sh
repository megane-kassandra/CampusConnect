#!/bin/bash
ROOT="$HOME/Bureau/TP INF4057/CampusConnect"
GW="$ROOT/gateway_service"
B='\033[1m'; G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; N='\033[0m'

echo -e "${B}═══ A. Contenu BRUT de tous les fichiers de config ═══${N}"
find "$GW/src/main/resources" -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.properties" \) -print -exec sh -c 'echo "─────"; cat "$1"; echo' _ {} \;

echo -e "\n${B}═══ B. Dépendances réelles (spring-boot-starter-web ? gateway-mvc ?) ═══${N}"
grep -nE 'spring-boot-starter-web|spring-cloud-starter-gateway|spring-boot-starter-actuator|spring-cloud-starter-netflix' "$GW/pom.xml"
echo "→ Test de pièges fréquents :"
grep -q 'spring-boot-starter-web' "$GW/pom.xml" && echo -e "${R}✗ spring-boot-starter-web PRÉSENT → force Tomcat (servlet)${N}" || echo -e "${G}✔ Pas de starter-web${N}"
grep -q 'spring-cloud-starter-gateway-mvc' "$GW/pom.xml" && echo -e "${R}✗ spring-cloud-starter-gateway-mvc détecté → PAS de /actuator/gateway${N}" || true

echo -e "\n${B}═══ C. Classe réellement utilisée au runtime (Tomcat vs Netty) ═══${N}"
grep -E 'Tomcat started|Netty started|ReactiveWebServerFactory|ServletWebServerFactory' "$ROOT/gateway-server.log" | tail -3

echo -e "\n${B}═══ D. Classes suspectes dans le log (RestTemplate = servlet) ═══${N}"
grep -oE 'HttpServerErrorException|WebClientResponseException|dispatcherServlet|DispatcherHandler' "$ROOT/gateway-server.log" | sort | uniq -c

echo -e "\n${B}═══ E. Où sont chargées les routes ? (spring.config.import, bootstrap, profils) ═══${N}"
grep -rE 'config\.import|configserver|discovery\.locator|bootstrap' "$GW/src/main/resources" 2>/dev/null || echo "(rien)"
find "$GW/src/main/resources" -name "bootstrap*" -o -name "application-*" 2>/dev/null

echo -e "\n${B}═══ F. Copie de la config server si accessible ═══${N}"
curl -sS --max-time 3 http://localhost:8888/api-gateway/default 2>/dev/null | head -40 || echo "config-server inaccessible"
curl -sS --max-time 3 http://localhost:8888/actuator/health 2>/dev/null || echo "health KO"

echo -e "\n${B}═══ G. Dernier état interne du gateway ═══${N}"
grep -E 'RouteDefinition|RouteDefinitionLocator|Loaded route|Refresh routes' "$ROOT/gateway-server.log" | tail -10 || echo "(aucune trace de RouteDefinition)"

echo -e "\n${B}═══ H. Services Eureka (statut STUDENT-SERVICE) ═══${N}"
curl -sS --max-time 3 -H 'Accept: application/json' http://localhost:8761/eureka/apps 2>/dev/null \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(" •",a["name"],"→",len(a.get("instance",[])),"instance(s)") for a in d.get("applications",{}).get("application",[])]' 2>/dev/null \
  || echo "Eureka KO"
