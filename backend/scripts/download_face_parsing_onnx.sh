#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${FACE_PARSING_DEST:-$ROOT/models/face_parsing_resnet18.onnx}"
URL="${FACE_PARSING_URL:-https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx}"
mkdir -p "$(dirname "$DEST")"
echo "Downloading $URL -> $DEST"
curl -fL --retry 3 -o "$DEST" "$URL"
echo "Done."
