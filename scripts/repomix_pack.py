"""
repomix_pack.py — Packages codebases into an AI-ready context file using Repomix.
Usage:
    python repomix_pack.py [target_dir] [--style xml|markdown|plain] [--output file] [--copy]
"""

import sys
import os
import argparse
import subprocess
import shutil

def main():
    parser = argparse.ArgumentParser(description="Package codebase with Repomix for LiteLLM & Sektor9 agents.")
    parser.add_argument("target_dir", nargs="?", default=".", help="Directory to pack (default: current directory)")
    parser.add_argument("--style", choices=["xml", "markdown", "plain"], default="xml", help="Output format style")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: repomix-output.<style>)")
    parser.add_argument("--copy", "-c", action="store_true", help="Copy packed output to system clipboard")
    parser.add_argument("--compress", action="store_true", help="Compress code (strip comments & empty lines)")

    args = parser.parse_args()
    target_dir = os.path.abspath(args.target_dir)

    if not os.path.exists(target_dir):
        print(f"Error: Target directory does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    ext = "xml" if args.style == "xml" else ("md" if args.style == "markdown" else "txt")
    output_file = args.output or os.path.join(target_dir, f"repomix-output.{ext}")

    print(f"[*] Packaging {target_dir} -> {output_file} (style: {args.style})...")

    cmd = ["npx", "-y", "repomix", target_dir, "--style", args.style, "--output", output_file]
    if args.compress:
        cmd.extend(["--remove-comments", "--remove-empty-lines"])

    # If local repomix.config.json exists, pass it
    config_candidate = os.path.join(target_dir, "repomix.config.json")
    if not os.path.exists(config_candidate):
        global_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "repomix.config.json")
        if os.path.exists(global_config):
            cmd.extend(["--config", global_config])

    try:
        proc = subprocess.run(cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running repomix: {e}", file=sys.stderr)
        sys.exit(e.returncode)

    if os.path.exists(output_file):
        size_bytes = os.path.getsize(output_file)
        size_kb = size_bytes / 1024
        print(f"[+] Successfully packed! File size: {size_kb:.1f} KB")

        if args.copy:
            try:
                import pyperclip
                with open(output_file, "r", encoding="utf-8") as f:
                    pyperclip.copy(f.read())
                print("[+] Copied packed codebase to clipboard!")
            except ImportError:
                # Windows clip fallback
                if sys.platform == "win32":
                    subprocess.run(f"clip < \"{output_file}\"", shell=True)
                    print("[+] Copied packed codebase to clipboard (via clip)!")

if __name__ == "__main__":
    main()
