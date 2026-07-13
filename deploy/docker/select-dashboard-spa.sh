#!/bin/sh
set -eu
echo "allbot_release_sha=${ALLBOT_RELEASE_SHA:-unknown}"

case "${DASHBOARD_FRONTEND_MODE:-dashboard}" in
  dashboard)
    index_file=index.html
    config_file=/opt/allbot-nginx/dashboard.conf.template
    ;;
  qqcc)
    index_file=index.qqcc-config.html
    config_file=/opt/allbot-nginx/qqcc.conf.template
    ;;
  *) echo "invalid DASHBOARD_FRONTEND_MODE" >&2; exit 2 ;;
esac

rm -rf /usr/share/nginx/html/*
cp -a /opt/allbot-spa/. /usr/share/nginx/html/
if [ "$index_file" != index.html ]; then
  cp "/usr/share/nginx/html/$index_file" /usr/share/nginx/html/index.html
fi
cp "$config_file" /etc/nginx/templates/default.conf.template
