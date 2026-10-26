#!/usr/bin/env bash
# Prepares the local Garage node: one-node layout, the two buckets of ADR-0019 and an access
# key, then prints the variables for apps/api/.env. Idempotent.
# Usage: bash infra/garage/init.sh [container]   (default container: trovelya-garage-1)
# GARAGE_ENDPOINT (S3 API as reached by GARAGE_PYTHON), GARAGE_CORS_ORIGIN (the web app) and
# GARAGE_PYTHON (a Python with boto3) default to the local development stack.
set -euo pipefail
CONTAINER="${1:-trovelya-garage-1}"
ENDPOINT="${GARAGE_ENDPOINT:-http://localhost:3900}"
CORS_ORIGIN="${GARAGE_CORS_ORIGIN:-http://localhost:3000}"
PYTHON="${GARAGE_PYTHON:-uv run --project $(dirname "$0")/../../apps/api python}"
garage() { docker exec -e RUST_LOG=warn "$CONTAINER" /garage "$@"; }

for _ in $(seq 1 30); do garage status >/dev/null 2>&1 && break; sleep 1; done
NODE="$(garage node id -q | cut -d@ -f1)"
# `layout show` prints the first 16 characters of the node id only.
if ! garage layout show | grep -q "^${NODE:0:16}"; then
  garage layout assign -z local -c 1G "$NODE" >/dev/null
  garage layout apply --version 1 >/dev/null
fi
for bucket in trovelya-originals trovelya-variants; do
  garage bucket info "$bucket" >/dev/null 2>&1 || garage bucket create "$bucket" >/dev/null
done
garage key info trovelya-local >/dev/null 2>&1 || garage key create trovelya-local >/dev/null
for bucket in trovelya-originals trovelya-variants; do
  garage bucket allow --read --write --owner "$bucket" --key trovelya-local >/dev/null
done
# Variants are public (ADR-0019): served read-only as a static website.
garage bucket website --allow trovelya-variants >/dev/null
KEY="$(garage key info trovelya-local --show-secret)"
KEY_ID="$(echo "$KEY" | awk '/Key ID/ {print $NF}')"
SECRET="$(echo "$KEY" | awk '/Secret key/ {print $NF}')"
# The browser uploads straight to `originals` (as on R2, infra/r2/README.md): CORS for the
# local web origin. Garage has no CLI command for it; the S3 API does.
export KEY_ID SECRET ENDPOINT CORS_ORIGIN
$PYTHON - <<'PY'
import os

import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["ENDPOINT"],
    region_name="garage",
    aws_access_key_id=os.environ["KEY_ID"],
    aws_secret_access_key=os.environ["SECRET"],
)
rule = {
    "AllowedOrigins": [os.environ["CORS_ORIGIN"]],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "MaxAgeSeconds": 3600,
}
s3.put_bucket_cors(Bucket="trovelya-originals", CORSConfiguration={"CORSRules": [rule]})
PY
echo "STORAGE_PROVIDER=s3"
echo "STORAGE_ENDPOINT=$ENDPOINT"
echo "STORAGE_REGION=garage"
echo "STORAGE_ACCESS_KEY_ID=$KEY_ID"
echo "STORAGE_SECRET_ACCESS_KEY=$SECRET"
echo "STORAGE_BUCKET_ORIGINALS=trovelya-originals"
echo "STORAGE_BUCKET_VARIANTS=trovelya-variants"
echo "MEDIA_PUBLIC_URL=http://trovelya-variants.web.garage.localhost:3902"
