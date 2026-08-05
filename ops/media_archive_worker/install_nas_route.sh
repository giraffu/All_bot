#!/usr/bin/env bash
set -euo pipefail

connection="${ALLBOT_NAS_ROUTE_CONNECTION:-netplan-eno1}"
destination="192.168.1.150/32"

if ! nmcli -g ipv4.routes connection show "$connection" | tr ',' '\n' | grep -Fq "$destination"; then
  nmcli connection modify "$connection" +ipv4.routes "$destination"
fi
nmcli device reapply eno1
route="$(ip -4 route get 192.168.1.150)"
grep -Fq 'dev eno1' <<<"$route"
grep -Fq 'src 192.168.1.115' <<<"$route"
printf '%s\n' "$route"
