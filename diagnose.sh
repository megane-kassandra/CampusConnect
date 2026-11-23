#!/bin/bash
# ============================================================
#  Script de diagnostic CampusConnect - Gateway Actuator 404
# ============================================================

ROOT="$HOME/Bureau/TP INF4057/CampusConnect"
GW="$ROOT/gateway_service"
LOG="$ROOT/gateway-server.log"

C_RED='\033[0;31m'; C_GRN='\033[0;32m'; C_YEL='\033[1;33m'
C_BLU='\033[0;34m'; C_CYN='\033[0;36m'; C_RST='\033[0m'; C_BLD='\033[1m'

section() { echo -e "\n${C_BLU}══════════════════════════════════════════════════════════${C_RST}"; \
            echo -e "${C_BLD}${C_CYN} $1${C_RST}"; \
            echo -e "${C_BLU}══════════════════════════════════════════════════════════${C_RST}"; }
ok()   { echo -e "  ${C_GRN}✔${C_RST} $1"; }
ko()   { echo -e "  ${C_RED}�’${C_RST} $1"; }
warn() { echo -e "  ${C_YEL}⚠${C_RST} $1"; }
info() { echo -e "  ${C_CYN}ℹ${C_RST} $1"; }

# ============================================================
section "1. Structure & fichiers du gateway_service"

if [ ! -d "$GW" ]; then
    ko "Dossier $GW introuvable !"
    exit 1
fi
ok "Dossier gateway_service présent"

echo "  → Fichiers de configuration trouvés :"
find "$GW/src/main/resources" -maxdepth 2 -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.properties" \) 2>/dev/null \
    | sed 's/^/      /' || warn "Aucun fichier de config trouvé"

# ============================================================
section "2. Analyse du pom.xml du gateway"

POM="$GW/pom.xml"
if [ ! -f "$POM" ]; then
    ko "pom.xml introuvable !"
else
    ok "pom.xml trouvé"

    # --- Versions Spring Boot / Spring Cloud ---
    BOOT_VER=$(grep -A2 '<parent>' "$POM" | grep -oP '<version>\K[^<]+' | head -1)
    CLOUD_VER=$(grep -oP 'spring-cloud.version>\K[^<]+' "$POM" | head -1)
    [[ -z "$CLOUD_VER" ]] && CLOUD_VER=$(grep -A2 'spring-cloud-dependencies' "$POM" | grep -oP '<version>\K[^<]+' | head -1)

    echo "  → Spring Boot version  : ${BOOT_VER:-<non détectée>}"
    echo "  → Spring Cloud version : ${CLOUD_VER:-<non détectée>}"

    # Vérification cohérence Boot <-> Cloud
    case "$BOOT_VER" in
        3.5.*) [[ "$CLOUD_VER" == 2025.* ]] && ok "Compatibilité Boot 3.5 / Cloud 2025.x" || warn "Boot 3.5 attend Cloud 2025.x" ;;
        3.4.*) [[ "$CLOUD_VER" == 2024.* ]] && ok "Compatibilité Boot 3.4 / Cloud 2024.x" || warn "Boot 3.4 attend Cloud 2024.x" ;;
        3.3.*) [[ "$CLOUD_VER" == 2023.* ]] && ok "Compatibilité Boot 3.3 / Cloud 2023.x" || warn "Boot 3.3 attend Cloud 2023.x" ;;
        "")    warn "Impossible de détecter la version Spring Boot" ;;
    esac

    # --- Présence des dépendances critiques ---
    echo "  → Dépendances clés :"
    grep -q 'spring-boot-starter-actuator' "$POM" && ok "spring-boot-starter-actuator présent" || ko "spring-boot-starter-actuator MANQUANT"
    grep -q 'spring-cloud-starter-gateway'  "$POM" && ok "spring-cloud-starter-gateway présent"  || ko "spring-cloud-starter-gateway MANQUANT"
    grep -q 'spring-cloud-starter-netflix-eureka-client' "$POM" && ok "eureka-client présent" || warn "eureka-client absent"
    grep -q 'spring-boot-starter-security' "$POM" && warn "spring-boot-starter-security présent (peut bloquer /actuator/gateway)" || ok "Pas de security (ne bloque pas /actuator)"

    # --- Ancien starter Gateway MVC (à éviter) ---
    if grep -q 'spring-cloud-starter-gateway-mvc' "$POM"; then
        ko "spring-cloud-starter-gateway-mvc détecté : incompatible avec l'endpoint /actuator/gateway (qui nécessite WebFlux)"
    fi
fi

# ============================================================
section "3. Analyse des fichiers application*.yml"

for f in "$GW"/src/main/resources/application*.yml "$GW"/src/main/resources/application*.yaml; do
    [ -f "$f" ] || continue
    echo -e "\n${C_BLD}  ── $f ──${C_RST}"

    # --- endpoint gateway activé ? ---
    if grep -qE 'endpoint:[[:space:]]*$' "$f" && grep -qE 'gateway:[[:space:]]*$' "$f"; then
        if grep -qE 'access:[[:space:]]*(read-only|unrestricted)' "$f"; then
            ok "management.endpoint.gateway.access défini"
        elif grep -qE 'enabled:[[:space:]]*true' "$f"; then
            warn "management.endpoint.gateway.enabled=true utilisé (OBSOLÈTE en Spring Cloud 2025.x, préférer access: read-only)"
        else
            ko "Bloc endpoint.gateway présent mais sans 'access:' → endpoint désactivé par défaut"
        fi
    else
        ko "Bloc 'management.endpoint.gateway' ABSENT → l'endpoint /actuator/gateway n'est pas activé"
    fi

    # --- endpoint exposé ? ---
    if grep -qE 'exposure:[[:space:]]*$' "$f" && grep -A3 'exposure:' "$f" | grep -qE 'include:.*gateway'; then
        ok "gateway exposé via management.endpoints.web.exposure.include"
    else
        ko "gateway NON exposé (include ne contient pas 'gateway')"
    fi

    # --- routes définies avec quel préfixe ? ---
    if grep -qE 'spring:[[:space:]]*$' "$f" && grep -qE 'cloud:[[:space:]]*$' "$f"; then
        if grep -qE 'server:[[:space:]]*$' "$f" && grep -A2 'server:' "$f" | grep -q 'webflux:'; then
            ok "Préfixe routes : spring.cloud.gateway.server.webflux.* (moderne)"
        elif grep -qE '^\s+gateway:' "$f"; then
            if grep -qE 'spring.*cloud.*gateway.*routes' "$f" || grep -B1 -A1 'routes:' "$f" | grep -q 'gateway:'; then
                warn "Préfixe 'spring.cloud.gateway.routes' (ancien) → IGNORÉ en Spring Cloud 2025.x"
            fi
        fi
    fi

    # --- afficher les routes ---
    echo -e "\n  ${C_BLD}Routes détectées :${C_RST}"
    grep -nE 'id:|uri:|predicates:|Path=' "$f" | sed 's/^/      /' || warn "Aucune route trouvée"

    # --- config eureka ---
    echo -e "\n  ${C_BLD}Config Eureka :${C_RST}"
    grep -nE 'eureka|defaultZone|service-url' "$f" | sed 's/^/      /' || warn "Aucune config Eureka"

    # --- port & application name ---
    echo -e "\n  ${C_BLD}Identité service :${C_RST}"
    grep -nE '^\s+(name|port):' "$f" | sed 's/^/      /'
done

# ============================================================
section "4. Analyse des logs (gateway-server.log)"

if [ -f "$LOG" ]; then
    ok "Log trouvé ($LOG)"
    echo "  → Erreurs/WARN récents :"
    grep -iE 'ERROR|WARN|Exception|Failed|Caused by' "$LOG" | tail -20 | sed 's/^/      /' \
        || info "Aucune erreur dans le log"

    echo -e "\n  → Lignes concernant l'actuator/gateway :"
    grep -iE 'actuator|endpoint|gateway.*route|RouteDefinition' "$LOG" | tail -15 | sed 's/^/      /' \
        || info "Aucune ligne trouvée"

    echo -e "\n  → Démarrage : quels endpoints exposés ?"
    grep -iE 'Exposing|Mapped.*actuator|Tomcat started|Netty started' "$LOG" | tail -10 | sed 's/^/      /'
else
    ko "Log $LOG introuvable"
fi

# ============================================================
section "5. Test des services en cours d'exécution"

for port in 8888 8761 8080; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        ok "Port $port en écoute"
    else
        ko "Port $port FERMÉ"
    fi
done

echo -e "\n  → Test HTTP services :"
for pair in "8888:config" "8761:eureka" "8080:gateway"; do
    port="${pair%%:*}"; name="${pair##*:}"
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:$port/actuator/health" 2>/dev/null)
    echo "      $name ($port) /actuator/health → HTTP $code"
done

# ============================================================
section "6. Test spécifique des endpoints du gateway"

echo "  → /actuator (liens disponibles) :"
LINKS=$(curl -sS --max-time 3 http://localhost:8080/actuator 2>/dev/null | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin).get("_links",{}).keys()))' 2>/dev/null)
echo "      $LINKS"
echo "$LINKS" | grep -q "gateway" && ok "Lien 'gateway' présent" || ko "Lien 'gateway' ABSENT"

echo -e "\n  → /actuator/gateway/routes :"
curl -sS -o /dev/null -w "      HTTP %{http_code}\n" --max-time 3 http://localhost:8080/actuator/gateway/routes

echo -e "\n  → /api/students/1 (routage) :"
curl -sS -o /tmp/resp.txt -w "      HTTP %{http_code}\n" --max-time 5 http://localhost:8080/api/students/1
echo "      Body : $(head -c 300 /tmp/resp.txt)"

# ============================================================
section "7. Vérification des routes chargées dans Eureka"

curl -sS --max-time 3 http://localhost:8761/eureka/apps 2>/dev/null \
  | grep -oP '<name>\K[^<]+' | sort -u | sed 's/^/      → /' \
  || warn "Impossible de joindre Eureka"

# ============================================================
section "8. RÉSUMÉ & CAUSES PROBABLES"

echo "Vérifiez les points marqués ${C_RED}�’${C_RST} ci-dessus. Les 3 causes les plus probables :"
echo ""
echo "  ${C_BLD}A.${C_RST} management.endpoint.gateway.access ABSENT → ajouter :"
echo "        management:"
echo "          endpoints:"
echo "            web:"
echo "              exposure:"
echo "                include: gateway"
echo "          endpoint:"
echo "            gateway:"
echo "              access: read-only"
echo ""
echo "  ${C_BLD}B.${C_RST} Préfixe routes obsolète (spring.cloud.gateway.routes) →"
echo "        en Spring Cloud 2025.x, utiliser spring.cloud.gateway.server.webflux.routes"
echo ""
echo "  ${C_BLD}C.${C_RST} spring-boot-starter-security présent sans configuration →"
echo "        autoriser /actuator/** dans la SecurityWebFilterChain"
echo ""
echo "  ${C_BLD}Note${C_RST} : le 500 sur /api/students/1 est NORMAL si le service students est down,"
echo "  le gateway renvoie 500 'Unable to find instance' par défaut."
echo "  Le 503 attendu nécessite un CircuitBreaker (Resilience4j) configuré."
