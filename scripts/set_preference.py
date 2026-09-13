#!/usr/bin/env python3
"""
Asks how you want refresh_models.py to pick between candidate models, and
saves it to .model_preferences.json (gitignored -- it's a personal setting,
not project config). Re-run any time to change your mind.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREF_PATH = ROOT / ".model_preferences.json"

MODES = {
    "1": ("auto", "Auto (recommended) — same as 'cheapest from the best': strong models only, cheapest among those"),
    "2": ("cheapest", "Cheapest — absolute lowest price among same-family candidates, even if a pricier one is newer"),
    "3": ("most_accurate", "Most accurate — always the newest/most capable version in the family, cost secondary"),
    "4": ("performance", "Performance — same as most_accurate here (no latency data in provider catalogs to optimize on separately)"),
    "5": ("cheapest_from_best", "Cheapest from the best — identical to Auto, spelled out for clarity"),
    "6": ("custom", "Custom — never auto-apply anything; refresh_models.py always behaves as --dry-run regardless of flags"),
}


def main():
    print("How should the model auto-refresher choose between candidates?\n")
    for k, (_, desc) in MODES.items():
        print(f"  {k}) {desc}")
    choice = input("\nPick 1-6 [1]: ").strip() or "1"
    if choice not in MODES:
        print("Not a valid choice, nothing changed.")
        sys.exit(1)
    mode, _ = MODES[choice]
    PREF_PATH.write_text(json.dumps({"mode": mode}, indent=2), encoding="utf-8")
    print(f"\nSaved: {mode}. Change it any time by re-running this script.")


if __name__ == "__main__":
    main()
