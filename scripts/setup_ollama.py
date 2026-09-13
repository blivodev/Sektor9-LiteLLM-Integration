#!/usr/bin/env python3
"""
setup_ollama.py - optional local-LLM integration.

WHAT THIS IS FOR: running a model on YOUR OWN hardware costs $0 per token
(vs. every cloud provider in config.yaml), but only makes sense if your
GPU/RAM can actually run something useful at a usable speed. This script:

  1. Detects your hardware (NVIDIA GPU VRAM if present, else system RAM)
     and recommends a specific Ollama model size that fits it - or tells
     you honestly that local models aren't worth it on this machine.
  2. Installs Ollama if it's missing (with your OK).
  3. Pulls the recommended model.
  4. Registers it in config.yaml as a NEW LAST-RESORT fallback for the
     Code and Ask modes only (not Debug/Plan/Orchestrator - those benefit
     more from strong reasoning that a small local model won't match, so
     this intentionally doesn't touch them). It never becomes the PRIMARY
     model on its own - it's an always-available, zero-cost backstop for
     when every configured cloud provider is down or out of credit.

This is entirely opt-in and reversible: it only edits config.yaml (a git
commit, like everything else here) and only after you confirm the plan it
prints. Nothing runs automatically just by having this file present.

Usage:
    python scripts/setup_ollama.py --check       # just show the hardware read + recommendation, change nothing
    python scripts/setup_ollama.py                # full interactive setup
    python scripts/setup_ollama.py --remove       # remove local-ollama from config.yaml's fallbacks
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Missing dependency. Install with:\n  pip install pyyaml\n", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"

OLLAMA_MODEL_NAME = "local-ollama"
OLLAMA_HOST = "host.docker.internal"  # the container reaches YOUR machine's Ollama through this
OLLAMA_PORT = 11434

# (min_vram_gb, min_ram_gb, ollama_model_tag, human description)
# Checked in order, first match wins. VRAM takes priority over RAM when a
# usable NVIDIA GPU is detected; RAM-only is the CPU-inference fallback.
TIERS = [
    (16, 32, "qwen2.5-coder:14b", "14B coding model - GPU with 16GB+ VRAM"),
    (8, 16, "qwen2.5-coder:7b", "7B coding model - GPU with 8GB+ VRAM, or 16GB+ RAM CPU-only"),
    (0, 32, "qwen2.5-coder:7b", "7B coding model, CPU-only - usable but noticeably slower than the cloud models"),
]
MIN_RAM_GB_WORTH_IT = 16  # below this, local inference is too slow/limited to be worth the disk space


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def detect_nvidia_vram_gb() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
        if r.returncode != 0:
            return None
        first_line = r.stdout.strip().splitlines()[0]
        return float(first_line.strip()) / 1024  # MiB -> GiB
    except (IndexError, ValueError, FileNotFoundError):
        return None


def detect_ram_gb() -> float | None:
    system = platform.system()
    try:
        if system == "Windows":
            # wmic is gone on recent Windows builds; Get-CimInstance is its
            # modern replacement and works where wmic no longer exists.
            r = run([
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize",
            ])
            out = r.stdout.strip()
            if out.isdigit():
                return float(out) / (1024 * 1024)  # KB -> GB
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = float(line.split()[1])
                        return kb / (1024 * 1024)
        elif system == "Darwin":
            r = run(["sysctl", "-n", "hw.memsize"])
            if r.returncode == 0 and r.stdout.strip().isdigit():
                return float(r.stdout.strip()) / (1024 ** 3)
    except Exception:
        pass
    return None


def recommend() -> dict:
    vram = detect_nvidia_vram_gb()
    ram = detect_ram_gb()

    for min_vram, min_ram, model, desc in TIERS:
        if vram is not None and vram >= min_vram and min_vram > 0:
            return {"worth_it": True, "model": model, "why": desc, "vram_gb": vram, "ram_gb": ram}
    if ram is not None and ram >= MIN_RAM_GB_WORTH_IT:
        # last tier (CPU-only) is the RAM-based fallback
        min_vram, min_ram, model, desc = TIERS[-1]
        return {"worth_it": True, "model": model, "why": desc, "vram_gb": vram, "ram_gb": ram}

    return {
        "worth_it": False,
        "model": None,
        "why": "Not enough detected VRAM/RAM to run a useful local model at a usable speed.",
        "vram_gb": vram,
        "ram_gb": ram,
    }


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def ollama_running() -> bool:
    try:
        import urllib.request

        urllib.request.urlopen(f"http://localhost:{OLLAMA_PORT}/api/version", timeout=2)
        return True
    except Exception:
        return False


def install_ollama() -> bool:
    system = platform.system()
    print("Installing Ollama...")
    if system == "Windows":
        r = run(["winget", "install", "-e", "--id", "Ollama.Ollama"])
    elif system in ("Linux", "Darwin"):
        # Avoid shell=True (and the shell pipe) entirely: fetch the script's
        # bytes ourselves and feed them to `sh` directly via stdin.
        import urllib.request

        try:
            script = urllib.request.urlopen("https://ollama.com/install.sh", timeout=30).read()
        except Exception as e:
            print(f"Couldn't download the install script: {e}")
            return False
        r = subprocess.run(["sh"], input=script)
        return r.returncode == 0
    else:
        print(f"Unsupported OS for auto-install: {system}. Install manually from https://ollama.com/download")
        return False
    return r.returncode == 0


def pull_model(model: str) -> bool:
    print(f"Pulling {model} (this downloads several GB, may take a while)...")
    r = subprocess.run(["ollama", "pull", model])
    return r.returncode == 0


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict):
    CONFIG_PATH.write_text(yaml.dump(cfg, sort_keys=False, default_flow_style=False), encoding="utf-8")


def add_to_config(cfg: dict, model: str) -> dict:
    model_list = cfg["model_list"]
    if not any(e["model_name"] == OLLAMA_MODEL_NAME for e in model_list):
        model_list.append({
            "model_name": OLLAMA_MODEL_NAME,
            "litellm_params": {
                "model": f"ollama_chat/{model}",
                "api_base": f"http://{OLLAMA_HOST}:{OLLAMA_PORT}",
            },
        })

    fb_list = cfg.setdefault("router_settings", {}).setdefault("fallbacks", [])
    for mode in ("kilo-code", "kilo-ask"):
        for fb in fb_list:
            if mode in fb:
                if OLLAMA_MODEL_NAME not in fb[mode]:
                    fb[mode] = fb[mode] + [OLLAMA_MODEL_NAME]
                break
        else:
            fb_list.append({mode: [OLLAMA_MODEL_NAME]})
    return cfg


def remove_from_config(cfg: dict) -> dict:
    cfg["model_list"] = [e for e in cfg["model_list"] if e["model_name"] != OLLAMA_MODEL_NAME]
    for fb in cfg.get("router_settings", {}).get("fallbacks", []):
        for mode, chain in fb.items():
            fb[mode] = [m for m in chain if m != OLLAMA_MODEL_NAME]
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Only show hardware read + recommendation.")
    ap.add_argument("--remove", action="store_true", help="Remove local-ollama from config.yaml.")
    args = ap.parse_args()

    if args.remove:
        cfg = load_config()
        save_config(remove_from_config(cfg))
        print(f"Removed {OLLAMA_MODEL_NAME} from config.yaml (if it was there). Restart the litellm container.")
        return

    rec = recommend()
    vram_str = f"{rec['vram_gb']:.1f} GB" if rec["vram_gb"] else "no NVIDIA GPU detected"
    ram_str = f"{rec['ram_gb']:.1f} GB" if rec["ram_gb"] else "unknown"
    print(f"GPU VRAM: {vram_str}")
    print(f"System RAM: {ram_str}")
    print()

    if not rec["worth_it"]:
        print(f"Recommendation: skip local models on this machine. {rec['why']}")
        return

    print(f"Recommendation: {rec['model']} - {rec['why']}")
    if args.check:
        return

    proceed = input(f"\nSet this up as a zero-cost last-resort fallback for Code/Ask modes? (y/N): ")
    if proceed.strip().lower() != "y":
        print("Skipped, nothing changed.")
        return

    if not ollama_installed():
        if input("Ollama isn't installed. Install it now? (y/N): ").strip().lower() == "y":
            if not install_ollama():
                print("Install failed or needs a shell restart - install manually from https://ollama.com/download, then re-run this script.")
                return
        else:
            print("Skipped, nothing changed.")
            return

    if not ollama_running():
        print("Ollama doesn't appear to be running yet - start the Ollama app, then re-run this script.")
        return

    if not pull_model(rec["model"]):
        print(f"Failed to pull {rec['model']}. Check the error above, then re-run this script.")
        return

    cfg = load_config()
    save_config(add_to_config(cfg, rec["model"]))
    print(f"\nAdded {OLLAMA_MODEL_NAME} ({rec['model']}) to config.yaml as a last-resort fallback for Code/Ask.")
    print("Restart the container to pick it up: docker compose up -d --force-recreate litellm")
    print(f"Remove it later any time with: python {Path(__file__).name} --remove")


if __name__ == "__main__":
    main()
