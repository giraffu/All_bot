#!/bin/sh
set -eu

output=${1:-./generated-tls}
direct_ip=${MINIO_DIRECT_BIND_IP:-10.250.150.2}
existing_ca_dir=${ALLBOT_ARCHIVE_EXISTING_CA_DIR:-}
mkdir -p "$output/ca" "$output/certs/CAs"
if [ -n "$existing_ca_dir" ]; then
  install -m 600 "$existing_ca_dir/allbot-archive-ca.key" \
    "$output/ca/allbot-archive-ca.key"
  install -m 644 "$existing_ca_dir/allbot-archive-ca.crt" \
    "$output/ca/allbot-archive-ca.crt"
else
  openssl genrsa -out "$output/ca/allbot-archive-ca.key" 4096
  openssl req -x509 -new -nodes -key "$output/ca/allbot-archive-ca.key" -sha256 -days 3650 \
    -subj "/CN=AllBot Archive Internal CA" -out "$output/ca/allbot-archive-ca.crt"
fi
openssl genrsa -out "$output/certs/private.key" 4096
openssl req -new -key "$output/certs/private.key" -subj "/CN=192.168.1.150" -out "$output/minio.csr"
cat > "$output/minio.ext" <<EOF
subjectAltName=IP:192.168.1.150,IP:${direct_ip},DNS:minio
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in "$output/minio.csr" -CA "$output/ca/allbot-archive-ca.crt" \
  -CAkey "$output/ca/allbot-archive-ca.key" -CAcreateserial -out "$output/certs/public.crt" \
  -days 825 -sha256 -extfile "$output/minio.ext"
cp "$output/ca/allbot-archive-ca.crt" "$output/certs/CAs/allbot-archive-ca.crt"
chmod 600 "$output/ca/allbot-archive-ca.key" "$output/certs/private.key"
chmod 644 "$output/ca/allbot-archive-ca.crt" "$output/certs/public.crt" \
  "$output/certs/CAs/allbot-archive-ca.crt"
openssl x509 -in "$output/certs/public.crt" -noout -subject -issuer -ext subjectAltName
