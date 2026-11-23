#!/usr/bin/env bash
# Rassemble les informations utiles pour diagnostiquer le Config Server.
# Usage : ./debug-config-server.sh > diagnostic.txt 2>&1
# Les mots de passe ne sont jamais affichés.

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${CONFIG_REPO_LINK:-$HOME/campusconnect-config-repo}"
ENV_FILE="$HERE/.env.config"
LOG_FILE="$HERE/config-server.log"

section() { printf '\n===== %s =====\n' "$1"; }

section "Système"
uname -srm
java -version 2>&1 | head -3
mvn -version 2>&1 | head -3
git --version

section "Projet"
PROJECT=""
for d in config-server config_service config-service; do
  if [ -f "$HERE/$d/pom.xml" ]; then PROJECT="$HERE/$d"; break; fi
done
echo "Projet : ${PROJECT:-INTROUVABLE}"
if [ -n "$PROJECT" ]; then
  echo "--- fichiers sources ---"
  find "$PROJECT/src" -type f | sort
  echo "--- application.properties parasite ? (doit être absent) ---"
  ls "$PROJECT/src/main/resources/application.properties" 2>&1
  echo "--- versions dans le pom ---"
  grep -nE "<java.version>|spring-cloud.version|spring-boot-starter-parent" -A1 "$PROJECT/pom.xml" | head -12
  echo "--- packages et classe principale ---"
  grep -rhn "^package " "$PROJECT/src/main/java" 2>/dev/null
  grep -rn "@EnableConfigServer\|@SpringBootApplication" "$PROJECT/src/main/java" 2>/dev/null
  echo "--- application.yml copié dans target/classes ? ---"
  ls "$PROJECT/target/classes/application.yml" 2>&1
fi

section "Variables d'environnement (présence uniquement)"
if [ -f "$ENV_FILE" ]; then
  for v in ENCRYPT_KEY CONFIG_CLIENT_PASSWORD CONFIG_ADMIN_PASSWORD; do
    if grep -q "^$v=." "$ENV_FILE"; then echo "$v : défini"; else echo "$v : ABSENT"; fi
  done
else
  echo "$ENV_FILE : ABSENT (lancez ./run-config-server.sh une fois)"
fi

section "Dépôt de configuration"
echo "Chemin : $REPO"
ls -ld "$REPO" 2>&1
if [ -d "$REPO/.git" ]; then
  echo "--- branche ---"
  git -C "$REPO" branch --show-current
  echo "--- derniers commits ---"
  git -C "$REPO" log --oneline -5
  echo "--- fichiers à la racine ---"
  ls "$REPO"
  echo "--- modifications non commitées ---"
  git -C "$REPO" status --short
else
  echo "PAS de dépôt Git à cet emplacement"
fi

section "Ports"
echo "8888 (Config Server) :"
ss -ltnp 2>/dev/null | grep ':8888 ' || echo "  rien n'écoute"
echo "8080 :"
ss -ltnp 2>/dev/null | grep ':8080 ' || echo "  rien n'écoute"

section "Tests HTTP sur le port 8888"
if [ -f "$ENV_FILE" ]; then
  (
    set -a; source "$ENV_FILE"; set +a
    echo "1. health            : $(curl -s -m 5 -w ' [HTTP %{http_code}]' http://localhost:8888/actuator/health)"
    echo "2. sans identifiants : HTTP $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost:8888/student-service/dev)"
    echo "3. mauvais mot de passe : HTTP $(curl -s -m 5 -o /dev/null -w '%{http_code}' -u config-client:mauvais http://localhost:8888/student-service/dev)"
    BODY="$(curl -s -m 10 -u "config-client:${CONFIG_CLIENT_PASSWORD}" -w '\n[HTTP %{http_code}]' http://localhost:8888/student-service/dev)"
    echo "4. configuration student-service/dev :"
    echo "$BODY" | tail -1
    echo "$BODY" | sed '$d' | jq '{label, version, sources: [.propertySources[].name]}' 2>/dev/null || echo "$BODY" | head -c 600
    echo "5. client sur /encrypt (attendu 403) : HTTP $(curl -s -m 5 -o /dev/null -w '%{http_code}' -u "config-client:${CONFIG_CLIENT_PASSWORD}" -H 'Content-Type: text/plain' --data-binary 'x' http://localhost:8888/encrypt)"
    echo "6. admin sur /encrypt (attendu 200)  : HTTP $(curl -s -m 5 -o /dev/null -w '%{http_code}' -u "config-admin:${CONFIG_ADMIN_PASSWORD}" -H 'Content-Type: text/plain' --data-binary 'x' http://localhost:8888/encrypt)"
  )
else
  echo "Ignoré : pas de .env.config"
fi

section "Journal : lignes clés"
if [ -f "$LOG_FILE" ]; then
  grep -nE "profile|Tomcat initialized|Started |generated security password|BUILD|APPLICATION FAILED|Caused by|ERROR" "$LOG_FILE" \
    | sed -E 's/(generated security password: ).*/\1***/' | tail -30
  section "Journal : 60 dernières lignes"
  tail -60 "$LOG_FILE" | sed -E 's/(generated security password: ).*/\1***/'
else
  echo "Pas de $LOG_FILE (lancez : ./run-config-server.sh 2>&1 | tee config-server.log)"
fi

echo
echo "===== FIN DU DIAGNOSTIC ====="
