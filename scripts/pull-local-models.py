#!/usr/bin/env python3
"""Download official Ollama manifests/blobs using curl when daemon networking fails."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

root = Path(os.getenv("OLLAMA_MODELS", str(Path.home() / ".ollama/models")))
blobs = root / "blobs"
blobs.mkdir(parents=True, exist_ok=True)
for model, tag in (("qwen2.5", "0.5b"), ("llama3.2", "1b")):
    url = f"https://registry.ollama.ai/v2/library/{model}"
    raw = subprocess.check_output([
        "curl", "--fail", "--silent", "--show-error", "--location",
        "--retry", "3", "--connect-timeout", "15", "--max-time", "90",
        f"{url}/manifests/{tag}",
    ])
    manifest = json.loads(raw)
    for layer in [manifest["config"], *manifest["layers"]]:
        digest = layer["digest"]
        target = blobs / digest.replace(":", "-")
        if target.exists() and hashlib.file_digest(target.open("rb"), "sha256").hexdigest() == digest.split(":")[1]:
            continue
        partial = target.with_suffix(".download")
        print(f"Downloading {model}:{tag}: {layer['size']} bytes", flush=True)
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location", "--retry", "3",
            "--connect-timeout", "15", "--max-time", "900", "--output", str(partial),
            f"{url}/blobs/{digest}",
        ], check=True)
        with partial.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest.split(":")[1] or partial.stat().st_size != layer["size"]:
            raise RuntimeError(f"Checksum/size mismatch for {digest}")
        partial.replace(target)
    destination = root / "manifests/registry.ollama.ai/library" / model / tag
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.with_suffix(".download").write_bytes(raw)
    destination.with_suffix(".download").replace(destination)
    print(f"Ready: {model}:{tag}", flush=True)
