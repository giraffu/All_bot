#!/usr/bin/env bash
set -euo pipefail

container_name="${MINIO_CONTAINER_NAME:-deploy-minio-1}"
container_ip="$(docker inspect "$container_name" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
test -n "$container_ip"

iptables -N ALLBOT_MEDIA_ARCHIVE 2>/dev/null || true
iptables -F ALLBOT_MEDIA_ARCHIVE
iptables -A ALLBOT_MEDIA_ARCHIVE -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -A ALLBOT_MEDIA_ARCHIVE -s 192.168.1.115/32 -d "$container_ip" -p tcp -m multiport --dports 9000,9001 -j ACCEPT
iptables -A ALLBOT_MEDIA_ARCHIVE -s 192.168.1.105/32 -d "$container_ip" -p tcp --dport 9001 -j ACCEPT
iptables -A ALLBOT_MEDIA_ARCHIVE -d "$container_ip" -p tcp -m multiport --dports 9000,9001 -j REJECT
iptables -C DOCKER-USER -j ALLBOT_MEDIA_ARCHIVE 2>/dev/null || \
  iptables -I DOCKER-USER 1 -j ALLBOT_MEDIA_ARCHIVE
