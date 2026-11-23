#!/usr/bin/env bash
cd "$(dirname "$0")"
CONFIG=http://localhost:8888
ok(){ echo -e "\e[32m[OK]\e[0m $*"; }
ko(){ echo -e "\e[31m[KO]\e[0m $*"; }

if [ -z "$CONFIG_CLIENT_PASSWORD" ]; then
  read -rsp "Mot de passe config-client : " CONFIG_CLIENT_PASSWORD; echo
fi
AUTH="config-client:$CONFIG_CLIENT_PASSWORD"

echo "== 1. Sante des services"
# Ajoutez auth-service:8081 student-service:8082 (ports a adapter) quand ils existeront
for e in config-server:8888 eureka-server:8761 api-gateway:8080; do
  n=${e%%:*}; p=${e##*:}
  s=$(curl -s -m 3 localhost:$p/actuator/health | jq -r .status 2>/dev/null)
  [ "$s" = "UP" ] && ok "$n UP (:$p)" || ko "$n pas UP (:$p)"
done

echo; echo "== 2. Le config server sert les fichiers"
code=$(curl -s -o /dev/null -w "%{http_code}" $CONFIG/api-gateway/default)
[ "$code" = "401" ] && ok "sans identifiants -> 401 (securite active)" || ko "sans identifiants -> $code (401 attendu)"
for app in eureka-server api-gateway auth-service student-service; do
  for prof in default dev docker; do
    names=$(curl -s -m 5 -u "$AUTH" $CONFIG/$app/$prof | jq -r '.propertySources[].name' 2>/dev/null)
    if [ "$prof" = default ]; then f="/$app.yml"; else f="/$app-$prof.yml"; fi
    if echo "$names" | grep -q "$f"; then ok "$app/$prof -> $f"
    elif [ "$prof" = default ]; then ko "$app/default -> $f introuvable"
    else echo "  (i) $app/$prof : pas de fichier dedie"; fi
  done
done

echo; echo "== 3. Les clients ont contacte le config server (logs)"
for f in eureka-server.log gateway-server.log; do
  grep -aq "Located environment" "$f" 2>/dev/null && ok "$f : config recue" || ko "$f : pas de 'Located environment'"
done

echo; echo "== 4. Source configserver dans /actuator/env"
for p in 8761 8080; do
  curl -s -m 3 localhost:$p/actuator/env | jq -r '.propertySources[]?.name' 2>/dev/null | grep -qi configserver \
    && ok ":$p utilise configserver" || ko ":$p pas de source configserver (env expose ?)"
done

echo; echo "== 5. Enregistrements Eureka"
curl -s -H "Accept: application/json" localhost:8761/eureka/apps \
  | jq -r '.applications.application[]? | "  \(.name) -> \(.instance[0].status)"'

echo; echo "== 6. Routes de la gateway"
r=$(curl -s -m 3 localhost:8080/actuator/gateway/routes | jq 'if type=="array" then length else 0 end' 2>/dev/null)
[ "${r:-0}" -ge 1 ] && ok "$r route(s) chargee(s)" || ko "0 route chargee"
