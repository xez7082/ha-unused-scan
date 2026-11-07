#!/usr/bin/with-contenv bashio
bashio::log.info "Nettoyeur de configuration : demarrage (Ingress, port 8099)"
export PORT=8099
exec python3 /app/server.py
