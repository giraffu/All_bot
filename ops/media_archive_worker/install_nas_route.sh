#!/usr/bin/env bash
set -euo pipefail

# This installer is deliberately single-purpose. It must never manage the LAN
# management profile or any legacy netplan profile.
readonly connection="allbot-archive-direct"
readonly interface="eno1"
readonly local_address="10.250.150.1/30"
readonly local_ip="10.250.150.1"
readonly nas_ip="10.250.150.2"
readonly management_ips=("192.168.1.105" "192.168.1.115")
readonly nmcli_bin="${ALLBOT_NMCLI_BIN:-nmcli}"
readonly ip_bin="${ALLBOT_IP_BIN:-ip}"

mode="check"
case "${1:-}" in
  ""|--check) mode="check" ;;
  --apply) mode="apply" ;;
  *)
    printf 'usage: %s [--check|--apply]\n' "$0" >&2
    exit 2
    ;;
esac
if (($# > 1)); then
  printf 'usage: %s [--check|--apply]\n' "$0" >&2
  exit 2
fi

die() {
  printf 'refusing NAS route change: %s\n' "$*" >&2
  exit 1
}

profile_exists() {
  "$nmcli_bin" -t -f NAME connection show | grep -Fxq "$connection"
}

active_connections="$("$nmcli_bin" -t -f NAME,DEVICE connection show --active)"
target_addresses="$("$ip_bin" -o -4 address show dev "$interface")"
default_routes="$("$ip_bin" -4 route show default)"

# An installer must never replace another active profile on the target NIC.
while IFS=: read -r active_name active_device; do
  if [[ "$active_device" == "$interface" && "$active_name" != "$connection" ]]; then
    die "non-archive connection '$active_name' is active on $interface"
  fi
done <<<"$active_connections"

if grep -Eq "(^|[[:space:]])dev[[:space:]]+$interface([[:space:]]|$)" \
    <<<"$default_routes"; then
  die "$interface carries a default route"
fi

for management_ip in "${management_ips[@]}"; do
  if grep -Fq " $management_ip/" <<<"$target_addresses"; then
    die "$interface carries management address $management_ip"
  fi
done

ssh_server_ip=""
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  read -r _ _ ssh_server_ip _ <<<"$SSH_CONNECTION"
fi
if [[ -n "$ssh_server_ip" ]] && \
    grep -Fq " $ssh_server_ip/" <<<"$target_addresses"; then
  die "$interface carries current SSH server address $ssh_server_ip"
fi

if profile_exists; then
  bound_interface="$("$nmcli_bin" -g connection.interface-name connection show "$connection")"
  if [[ -n "$bound_interface" && "$bound_interface" != "$interface" ]]; then
    die "$connection is bound to unexpected interface '$bound_interface'"
  fi
fi

validate_direct_route() {
  local route
  route="$("$ip_bin" -4 route get "$nas_ip")"
  grep -Eq "(^|[[:space:]])dev[[:space:]]+$interface([[:space:]]|$)" \
    <<<"$route" || return 1
  grep -Eq "(^|[[:space:]])src[[:space:]]+$local_ip([[:space:]]|$)" \
    <<<"$route" || return 1
  if grep -Eq "(^|[[:space:]])via([[:space:]]|$)" <<<"$route"; then
    return 1
  fi
  printf '%s\n' "$route"
}

if [[ "$mode" == "check" ]]; then
  route="$(validate_direct_route)" || \
    die "$nas_ip is not routed directly through $interface from $local_ip"
  printf 'read-only preflight passed: %s\n' "$route"
  exit 0
fi

existed=false
was_active=false
created=false
mutated=false
committed=false
old_interface=""
old_autoconnect=""
old_ipv4_method=""
old_ipv4_addresses=""
old_ipv4_gateway=""
old_ipv4_routes=""
old_ipv4_never_default=""
old_ipv6_method=""

if profile_exists; then
  existed=true
  if grep -Fxq "$connection:$interface" <<<"$active_connections"; then
    was_active=true
  fi
  old_interface="$("$nmcli_bin" -g connection.interface-name connection show "$connection")"
  old_autoconnect="$("$nmcli_bin" -g connection.autoconnect connection show "$connection")"
  old_ipv4_method="$("$nmcli_bin" -g ipv4.method connection show "$connection")"
  old_ipv4_addresses="$("$nmcli_bin" -g ipv4.addresses connection show "$connection")"
  old_ipv4_gateway="$("$nmcli_bin" -g ipv4.gateway connection show "$connection")"
  old_ipv4_routes="$("$nmcli_bin" -g ipv4.routes connection show "$connection")"
  old_ipv4_never_default="$("$nmcli_bin" -g ipv4.never-default connection show "$connection")"
  old_ipv6_method="$("$nmcli_bin" -g ipv6.method connection show "$connection")"
fi

rollback() {
  local status="$?"
  trap - EXIT
  set +e
  if [[ "$mutated" == true && "$committed" != true ]]; then
    if [[ "$created" == true ]]; then
      "$nmcli_bin" connection down "$connection" >/dev/null 2>&1
      "$nmcli_bin" connection delete "$connection" >/dev/null 2>&1
    elif [[ "$existed" == true ]]; then
      if [[ "$was_active" != true ]]; then
        "$nmcli_bin" connection down "$connection" >/dev/null 2>&1
      fi
      "$nmcli_bin" connection modify "$connection" \
        connection.interface-name "$old_interface" \
        connection.autoconnect "$old_autoconnect" \
        ipv4.method "$old_ipv4_method" \
        ipv4.addresses "$old_ipv4_addresses" \
        ipv4.gateway "$old_ipv4_gateway" \
        ipv4.routes "$old_ipv4_routes" \
        ipv4.never-default "$old_ipv4_never_default" \
        ipv6.method "$old_ipv6_method" >/dev/null 2>&1
      if [[ "$was_active" == true ]]; then
        "$nmcli_bin" connection up "$connection" >/dev/null 2>&1
      fi
    fi
    printf 'archive profile rollback attempted after failed validation\n' >&2
  fi
  exit "$status"
}
trap rollback EXIT

if [[ "$existed" != true ]]; then
  created=true
  mutated=true
  "$nmcli_bin" connection add type ethernet ifname "$interface" \
    con-name "$connection" \
    ipv4.method manual ipv4.addresses "$local_address" \
    ipv4.never-default yes ipv6.method disabled
fi

mutated=true
"$nmcli_bin" connection modify "$connection" \
  connection.interface-name "$interface" \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses "$local_address" \
  ipv4.gateway "" \
  ipv4.routes "" \
  ipv4.never-default yes \
  ipv6.method disabled
"$nmcli_bin" connection up "$connection"

# Re-run every safety guard whose truth can change during activation.
post_addresses="$("$ip_bin" -o -4 address show dev "$interface")"
post_defaults="$("$ip_bin" -4 route show default)"
if grep -Eq "(^|[[:space:]])dev[[:space:]]+$interface([[:space:]]|$)" \
    <<<"$post_defaults"; then
  die "$interface gained a default route after activation"
fi
for management_ip in "${management_ips[@]}"; do
  if grep -Fq " $management_ip/" <<<"$post_addresses"; then
    die "$interface gained management address $management_ip after activation"
  fi
done
if [[ -n "$ssh_server_ip" ]] && \
    grep -Fq " $ssh_server_ip/" <<<"$post_addresses"; then
  die "$interface gained current SSH server address $ssh_server_ip after activation"
fi
route="$(validate_direct_route)" || \
  die "$nas_ip is not routed directly through $interface from $local_ip"

committed=true
trap - EXIT
printf 'archive direct link applied safely: %s\n' "$route"
