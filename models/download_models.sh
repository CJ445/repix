#!/usr/bin/env bash
# Downloads pinned ONNX model weights used by Repix.
# Run once during image build (see docker/backend.Dockerfile) or manually
# during local setup: `bash models/download_models.sh`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

download "https://huggingface.co/edgetools/ddcolor/resolve/main/ddcolor-tiny-fp16.onnx" \
  "ddcolor/ddcolor_tiny.onnx"

download "https://huggingface.co/SceneWorks/real-esrgan-onnx/resolve/main/real_esrgan_x2.onnx" \
  "realesrgan/realesrgan_x2plus.onnx"

download "https://huggingface.co/SceneWorks/real-esrgan-onnx/resolve/main/real_esrgan_x4.onnx" \
  "realesrgan/realesrgan_x4plus.onnx"

echo "Verifying checksums..."
sha256sum -c CHECKSUMS.sha256

echo "All models present and verified."
