#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

find ./output -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
