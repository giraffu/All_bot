#!/usr/bin/env bash
set -euo pipefail

connection="${ALLBOT_NAS_ROUTE_CONNECTION:-allbot-archive-direct}"
legacy_connection="${ALLBOT_NAS_LEGACY_CONNECTION:-netplan-eno1}"
interface="${ALLBOT_NAS_ROUTE_INTERFACE:-eno1}"
local_address="${ALLBOT_NAS_DIRECT_LOCAL_ADDRESS:-10.250.150.1/30}"
local_ip="${local_address%/*}"
nas_ip="${ALLBOT_NAS_DIRECT_IP:-10.250.150.2}"

if ! nmcli -t -f NAME connection show | grep -Fxq "$connection"; then
  nmcli connection add type ethernet ifname "$interface" con-name "$connection" \
    ipv4.method manual ipv4.addresses "$local_address" \
    ipv4.never-default yes ipv6.method disabled
fi
nmcli connection modify "$connection" \
  connection.interface-name "$interface" \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses "$local_address" \
  ipv4.gateway "" \
  ipv4.routes "" \
  ipv4.never-default yes \
  ipv6.method disabled
if nmcli -t -f NAME connection show | grep -Fxq "$legacy_connection"; then
  nmcli connection modify "$legacy_connection" connection.autoconnect no
fi
nmcli connection up "$connection"
route="$(ip -4 route get "$nas_ip")"
grep -Fq "dev $interface" <<<"$route"
grep -Fq "src $local_ip" <<<"$route"
printf '%s\n' "$route"
