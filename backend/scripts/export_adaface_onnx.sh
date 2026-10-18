#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/../venv/bin/python}"
DEST="${ADAFACE_DEST:-$ROOT/models/adaface_ir101_webface12m.onnx}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

"$PY" -m pip install -q --target "$WORK/deps" --no-deps omegaconf fvcore iopath yacs tabulate termcolor portalocker antlr4-python3-runtime==4.9.3
"$PY" - "$WORK" "$DEST" <<'EOF'
import sys
work, dest = sys.argv[1], sys.argv[2]
from huggingface_hub import snapshot_download
src = snapshot_download(
    "minchul/cvlface_adaface_ir101_webface12m",
    local_dir=f"{work}/adaface",
    allow_patterns=["models/*", "models/**", "pretrained_model/*"],
)
sys.path[:0] = [f"{work}/deps", src]
import torch
from models.iresnet.model import IR_101

net = IR_101(input_size=(112, 112), output_dim=512)
state = torch.load(f"{src}/pretrained_model/model.pt", map_location="cpu", weights_only=False)
net.load_state_dict({k.removeprefix("net."): v for k, v in state.items()})
net.eval()
torch.onnx.export(
    net, torch.randn(1, 3, 112, 112), dest,
    input_names=["input"], output_names=["emb"],
    dynamic_axes={"input": {0: "n"}, "emb": {0: "n"}}, opset_version=17,
)
print("wrote", dest)
EOF
