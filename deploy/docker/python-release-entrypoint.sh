#!/bin/sh
set -eu
echo "allbot_release_sha=${ALLBOT_RELEASE_SHA:-unknown}"
exec "$@"
