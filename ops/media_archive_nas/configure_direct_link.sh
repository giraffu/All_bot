#!/usr/bin/env bash
set -euo pipefail

interface="${ALLBOT_NAS_DIRECT_INTERFACE:-eth0}"
address="${ALLBOT_NAS_DIRECT_ADDRESS:-10.250.150.2/30}"

ip link set "$interface" up
ip address replace "$address" dev "$interface"
ip -4 address show dev "$interface" | grep -Fq "inet $address"
