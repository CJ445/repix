#!/usr/bin/env bash
# Downloads pinned ONNX model weights used by Repix.
# Run once during image build (see docker/backend.Dockerfile) or manually
# during local setup: `bash models/download_models.sh`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Mirror of the pinned model files (provenance and licenses: see the repo's model card).
# Override MODEL_BASE_URL to use another mirror with the same layout; the checksums below
# are verified either way.
MODEL_BASE_URL="${MODEL_BASE_URL:-https://huggingface.co/thecyriljacob/repix-dependency-models/resolve/v1}"

mkdir -p ddcolor realesrgan

download() {
  local url="$1" dest="$2"
  if [ -f "$dest" ]; then
    echo "Already present: $dest"
    return
  fi
  echo "Downloading $dest ..."
  curl -sL --fail -o "$dest" "$url"
}

for model in ddcolor/ddcolor_large.onnx realesrgan/realesrgan_x2plus.onnx realesrgan/realesrgan_x4plus.onnx; do
  download "$MODEL_BASE_URL/$model" "$model"
done

echo "Verifying checksums..."
sha256sum -c CHECKSUMS.sha256

echo "All models present and verified."
