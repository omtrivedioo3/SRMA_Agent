#!/usr/bin/env python3
"""
Download MedGemma 4B to this machine.

Run this in YOUR OWN terminal (not through an agent/sandbox):

    cd ~/Work/"SRMA Agent"
    ./.venv/bin/python scripts/download_medgemma.py

Options:
    --full      also download the full bf16 weights (~8.5 GB, needs a GPU to run)
    --quant Q   pick a different quantization (default: Q4_K_M)
    --dest DIR  where to save (default: ./models)
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = PROJECT_ROOT / "models"

GGUF_REPO = "unsloth/medgemma-4b-it-GGUF"
FULL_REPO = "google/medgemma-4b-it"


def load_token() -> str:
    """Read HF_TOKEN from the environment, falling back to the local .env file."""
    token = os.environ.get("HF_TOKEN")
    if token:
        return token

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("HF_TOKEN=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()

    sys.exit(
        "ERROR: No HF_TOKEN found.\n"
        "  Either export HF_TOKEN=hf_... or add it to the .env file."
    )


def human(n: int) -> str:
    return f"{n / 1024**3:.2f} GB"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="also download full bf16 weights (~8.5 GB)")
    ap.add_argument("--quant", default="Q4_K_M",
                    help="quantization to download (default: Q4_K_M)")
    ap.add_argument("--dest", default=str(DEFAULT_DEST),
                    help="destination directory")
    args = ap.parse_args()

    try:
        from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    except ImportError:
        sys.exit("ERROR: run  ./.venv/bin/pip install huggingface_hub  first.")

    token = load_token()
    api = HfApi(token=token)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    # ---- sanity check: token + gated access -------------------------------
    print("Checking Hugging Face access ...")
    try:
        who = api.whoami()
        print(f"  logged in as: {who.get('name')}")
    except Exception as e:
        sys.exit(f"  TOKEN REJECTED: {e}")

    try:
        api.model_info(FULL_REPO)
        print(f"  gated access OK: {FULL_REPO}")
    except Exception as e:
        sys.exit(
            f"  NO ACCESS to {FULL_REPO}\n"
            f"  {type(e).__name__}: {str(e)[:200]}\n\n"
            f"  Fix: open https://huggingface.co/{FULL_REPO} and click\n"
            f"  'Acknowledge license', then re-run this script."
        )

    # ---- pick the GGUF file ------------------------------------------------
    print(f"\nLooking for a '{args.quant}' GGUF in {GGUF_REPO} ...")
    gguf_files = [f for f in api.list_repo_files(GGUF_REPO) if f.endswith(".gguf")]
    if not gguf_files:
        sys.exit("  No .gguf files found in that repo.")

    # Prefer an exact quant match; ignore the vision projector (mmproj),
    # which we do not need for text-only systematic-review work.
    candidates = [
        f for f in gguf_files
        if args.quant.lower() in f.lower() and "mmproj" not in f.lower()
    ]
    if not candidates:
        print("  Exact match not found. Available quantizations:")
        for f in sorted(gguf_files):
            print(f"    {f}")
        sys.exit(f"\n  Re-run with --quant matching one of the above.")

    chosen = sorted(candidates, key=len)[0]
    print(f"  selected: {chosen}")

    # ---- download the GGUF -------------------------------------------------
    print(f"\nDownloading {chosen} -> {dest}")
    print("(this is a few GB; progress bar below)\n")
    path = hf_hub_download(
        repo_id=GGUF_REPO,
        filename=chosen,
        local_dir=str(dest),
        token=token,
    )
    size = os.path.getsize(path)
    print(f"\nDONE: {human(size)} at {path}")

    # ---- optional: full bf16 weights --------------------------------------
    if args.full:
        full_dir = dest / "medgemma-4b-it"
        print(f"\nDownloading full bf16 weights -> {full_dir}")
        print("(~8.5 GB; safe to re-run if interrupted)\n")
        snapshot_download(
            repo_id=FULL_REPO,
            local_dir=str(full_dir),
            token=token,
            allow_patterns=["*.safetensors", "*.json", "*.model", "*.txt"],
            ignore_patterns=["*.gguf", "*.bin", "*.pth"],
        )
        print(f"\nDONE: {full_dir}")

    # ---- next steps --------------------------------------------------------
    modelfile = dest / "Modelfile"
    modelfile.write_text(
        f"FROM ./{Path(path).name}\n"
        "PARAMETER temperature 0.1\n"
        "PARAMETER num_ctx 8192\n"
    )

    print(f"""
================================================================
NEXT STEPS - register the model with Ollama so ADK can use it
================================================================

  1. Install Ollama (once):
       curl -fsSL https://ollama.com/install.sh | sh

  2. Build the model:
       cd {dest}
       ollama create medgemma -f Modelfile

  3. Test it:
       ollama run medgemma "List the 5 RoB 2 domains."

  A Modelfile has already been written for you at:
       {modelfile}
================================================================
""")


if __name__ == "__main__":
    main()
