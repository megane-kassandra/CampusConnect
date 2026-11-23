#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -z "$CONFIG_CLIENT_PASSWORD" ]; then
  read -rsp "Mot de passe config-client : " CONFIG_CLIENT_PASSWORD; echo
fi
export CONFIG_CLIENT_PASSWORD

for p in 8761 8080; do fuser -k ${p}/tcp >/dev/null 2>&1; done
sleep 3

start() {   # $1=nom du log  $2=dossier  $3=port
  (cd "$2" && nohup ./mvnw spring-boot:run > "../$1.log" 2>&1 &)
  for i in $(seq 1 60); do
    curl -sf localhost:$3/actuator/health >/dev/null && { echo "[OK] $1 UP (:$3)"; return 0; }
    sleep 2
  done
  echo "[KO] $1 ne démarre pas. Dernières erreurs :"
  grep -aE "ERROR|Caused by|APPLICATION FAILED|Unauthorized|Could not locate" "$1.log" | grep -avF "[ERROR]" | tail -8
  return 1
}
start eureka-server  eureka_service  8761
start gateway-server gateway_service 8080
