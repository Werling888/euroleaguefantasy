"""Equality guard for the build_dashboard refactor.

Usage:
    python scripts/verify_projection.py --save    # capture baseline (before refactor)
    python scripts/verify_projection.py --check    # assert output unchanged (after refactor)

The Tier C refactor only changes when/how often values are computed, never what.
Any diff in projections/coaches/defense is a bug.
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cache import load_cache
from src.injuries import ensure_injuries
from src.prices import ensure_prices
from src.project import build_dashboard

BASELINE = ROOT / "scripts" / ".projection_baseline.pkl"


def _build() -> dict[str, pd.DataFrame]:
    cache = load_cache(ROOT)
    if cache is None:
        raise SystemExit("No cache found. Run a Refresh in the app first.")
    try:
        cache["prices"] = ensure_prices(ROOT)
    except Exception:
        cache["prices"] = pd.DataFrame()
    try:
        cache["injuries"] = ensure_injuries(ROOT)
    except Exception:
        cache["injuries"] = pd.DataFrame()
    data = build_dashboard(cache)
    return {
        "projections": data.projections.reset_index(drop=True),
        "coaches": data.coaches.reset_index(drop=True),
        "defense": data.defense.reset_index(drop=True),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    frames = _build()
    if args.save:
        BASELINE.write_bytes(pickle.dumps(frames))
        for name, frame in frames.items():
            print(f"saved {name}: {frame.shape}")
        return
    if args.check:
        before = pickle.loads(BASELINE.read_bytes())
        for name in frames:
            pd.testing.assert_frame_equal(
                before[name], frames[name], check_exact=False, atol=1e-9,
                check_like=True, obj=name,
            )
            print(f"OK {name}: {frames[name].shape} identical")
        print("All frames identical — refactor is safe.")
        return
    parser.error("pass --save or --check")


if __name__ == "__main__":
    main()
