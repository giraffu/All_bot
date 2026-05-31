#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

EDGE_HOST="${EDGE_HOST:-root@100.88.57.122}"
EDGE_PORT="${EDGE_PORT:-22}"
EDGE_PROD_DIR="${EDGE_PROD_DIR:-/root/dist}"
SSH_KEY_PATH="${SSH_KEY_PATH:-./ssh_key/id_rsa.pem}"
SSH_CMD="ssh -i ${SSH_KEY_PATH} -p ${EDGE_PORT} -o StrictHostKeyChecking=no"
SCP_CMD="scp -i ${SSH_KEY_PATH} -P ${EDGE_PORT} -o StrictHostKeyChecking=no"
LOCAL_ARCHIVE=""
REMOTE_ARCHIVE="/tmp/allbot-edge-prod-dist.tar.gz"

if [ ! -f "$SSH_KEY_PATH" ]; then
  echo "❌ 未找到 SSH 私钥: $SSH_KEY_PATH"
  echo "   可通过 SSH_KEY_PATH=/path/to/key bash scripts/deploy-edge-prod.sh 覆盖。"
  exit 1
fi

cleanup() {
  if [ -n "$LOCAL_ARCHIVE" ] && [ -f "$LOCAL_ARCHIVE" ]; then
    rm -f "$LOCAL_ARCHIVE"
  fi
  $SSH_CMD "$EDGE_HOST" "rm -f '${REMOTE_ARCHIVE}'" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "🚀 开始构建生产 Web 静态资源..."
npm run build

echo "📁 确保边缘 VPS 生产目录存在: ${EDGE_PROD_DIR}"
$SSH_CMD "$EDGE_HOST" "mkdir -p '${EDGE_PROD_DIR}'"

echo "📦 打包 dist/..."
LOCAL_ARCHIVE="$(mktemp /tmp/allbot-edge-prod-dist.XXXXXX.tar.gz)"
tar -C dist -czf "$LOCAL_ARCHIVE" .

echo "📤 上传静态包到边缘 VPS..."
$SCP_CMD "$LOCAL_ARCHIVE" "${EDGE_HOST}:${REMOTE_ARCHIVE}"

echo "📂 解压并替换边缘 VPS 生产目录..."
$SSH_CMD "$EDGE_HOST" "rm -rf '${EDGE_PROD_DIR}'/* && tar -xzf '${REMOTE_ARCHIVE}' -C '${EDGE_PROD_DIR}'"

cat <<EOF
✅ 生产 Web 已同步到边缘 VPS。
   - Host: ${EDGE_HOST}
   - Directory: ${EDGE_PROD_DIR}
   - Domain: https://web.aivison.it.com
EOF
