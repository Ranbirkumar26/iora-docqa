#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/web"

npm ci
npm run build

cd "$ROOT_DIR"
rm -rf public
mkdir -p public
cp -R web/out/. public/
