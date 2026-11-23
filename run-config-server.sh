#!/usr/bin/env bash
# Lance le Config Server en mode Git (dépôt local).
# Usage : ./run-config-server.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${CONFIG_REPO_LINK:-$HOME/campusconnect-config-repo}"
ENV_FILE="$HERE/.env.config"

# 1. Le dépôt de configuration doit exister
if [ ! -d "$REPO/.git" ]; then
  echo "Dépôt de configuration introuvable : $REPO" >&2
  echo "Lancez d'abord : ./init-config-repo.sh" >&2
  exit 1
fi

# 2. Créer .env.config une seule fois
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
ENCRYPT_KEY=$(openssl rand -base64 32)
CONFIG_CLIENT_PASSWORD=client-dev
CONFIG_ADMIN_PASSWORD=admin-dev
EOF
  echo "Fichier créé : $ENV_FILE (ne le commitez pas)"
fi

# 3. Charger les variables
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export CONFIG_BACKEND=git
export CONFIG_GIT_URI="file://$REPO"

# 4. Trouver le projet Config Server
PROJECT_DIR=""
for d in config-server config_service config-service; do
  if [ -f "$HERE/$d/pom.xml" ]; then PROJECT_DIR="$HERE/$d"; break; fi
done
if [ -z "$PROJECT_DIR" ]; then
  echo "Projet Config Server introuvable dans $HERE" >&2
  echo "Dossiers cherchés : config-server, config_service, config-service" >&2
  exit 1
fi

# 5. Le port 8888 doit être libre
if ss -ltn 2>/dev/null | grep -q ':8888 '; then
  echo "Le port 8888 est déjà utilisé (un Config Server tourne peut-être déjà)." >&2
  exit 1
fi

echo "Dépôt  : $CONFIG_GIT_URI"
echo "Projet : $PROJECT_DIR"
cd "$PROJECT_DIR"
exec mvn spring-boot:run
