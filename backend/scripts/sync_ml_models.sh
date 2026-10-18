#!/usr/bin/env bash

set -euo pipefail
DEST="${1:?usage: sync_ml_models.sh user@host:/path/to/backend}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/models"

FILES=(
  adaface_ir101_webface12m.onnx  # face embeddings (verify / recognize)
  face_parsing_resnet18.onnx     # glasses segmentation
  pad_clip_head.json             # PAD classifier + thresholds
  pad_labels.json                # hand-reviewed PAD labels
  pad_clip_embeddings.npz        # PAD training cache (outlives deleted photos)
)
for f in "${FILES[@]}"; do
  [[ -f "$SRC/$f" ]] || { echo "missing $SRC/$f" >&2; exit 1; }
done

ssh "${DEST%%:*}" "mkdir -p '${DEST#*:}/models'"
rsync -av --progress "${FILES[@]/#/$SRC/}" "$DEST/models/"
echo "Done. On the target run: python manage.py check && restart uvicorn + celery."
