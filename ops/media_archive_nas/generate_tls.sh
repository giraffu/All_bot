#!/bin/sh
set -eu

output=${1:-./generated-tls}
mkdir -p "$output/ca" "$output/certs"
openssl genrsa -out "$output/ca/allbot-archive-ca.key" 4096
openssl req -x509 -new -nodes -key "$output/ca/allbot-archive-ca.key" -sha256 -days 3650 \
  -subj "/CN=AllBot Archive Internal CA" -out "$output/ca/allbot-archive-ca.crt"
openssl genrsa -out "$output/certs/private.key" 4096
openssl req -new -key "$output/certs/private.key" -subj "/CN=192.168.1.150" -out "$output/minio.csr"
cat > "$output/minio.ext" <<'EOF'
subjectAltName=IP:192.168.1.150,DNS:minio
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in "$output/minio.csr" -CA "$output/ca/allbot-archive-ca.crt" \
  -CAkey "$output/ca/allbot-archive-ca.key" -CAcreateserial -out "$output/certs/public.crt" \
  -days 825 -sha256 -extfile "$output/minio.ext"
chmod 600 "$output/ca/allbot-archive-ca.key" "$output/certs/private.key"
openssl x509 -in "$output/certs/public.crt" -noout -subject -issuer -ext subjectAltName
