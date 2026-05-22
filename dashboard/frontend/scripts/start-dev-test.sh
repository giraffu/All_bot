#!/bin/sh
set -eu

clean_npm_temp_dirs() {
  if [ ! -d node_modules ]; then
    return 0
  fi

  # Remove npm's interrupted hidden staging directories without touching source files.
  find node_modules -maxdepth 1 -mindepth 1 -type d -name '.*-*' -exec rm -rf {} + 2>/dev/null || true
}

reset_node_modules_contents() {
  if [ -d node_modules ]; then
    find node_modules -maxdepth 1 -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
  else
    mkdir -p node_modules
  fi
}

install_dependencies() {
  npm install --no-fund --no-audit --registry "$1"
}

PRIMARY_REGISTRY="${NPM_PRIMARY_REGISTRY:-https://registry.npmjs.org}"
FALLBACK_REGISTRY="${NPM_FALLBACK_REGISTRY:-https://registry.npmmirror.com}"

echo "Installing dashboard test frontend dependencies via ${PRIMARY_REGISTRY}"
clean_npm_temp_dirs

if ! install_dependencies "${PRIMARY_REGISTRY}"; then
  echo "npm install failed, resetting dashboard test node_modules volume and retrying once via ${FALLBACK_REGISTRY}..."
  reset_node_modules_contents
  clean_npm_temp_dirs
  install_dependencies "${FALLBACK_REGISTRY}"
fi

exec npm run dev -- --host 0.0.0.0 --port 5174 --strictPort
