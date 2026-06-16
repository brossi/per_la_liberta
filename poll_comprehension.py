"""Standalone progress poller for the P1 comprehension run (comprehension.py).

Independent of any agent session — run it in your own terminal:

    python poll_comprehension.py              # poll every 90s until complete
    python poll_comprehension.py --interval 60
    python poll_comprehension.py --once       # one snapshot, then exit

Progress is the count of saved raw responses in state/comprehension/raw vs the
computed total (passages × panel × samples). Cached reads from a prior run count
as already-done, so the bar starts at the resume floor, not zero.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from comprehension import parse_english, ENGLISH_MD, OUT_DIR, PANEL  # cheap: no model SDKs

RAW = os.path.join(OUT_DIR, "raw")
META = os.path.join(OUT_DIR, "run_meta.json")


def total_calls(samples: int) -> int:
    secs = parse_english(open(ENGLISH_MD, encoding="utf-8").read())
    passages = sum(len(s["passages"]) for s in secs)
    return passages * len(PANEL) * samples


def raw_count() -> int:
    try:
        return sum(1 for f in os.listdir(RAW) if f.endswith(".txt"))
    except FileNotFoundError:
        return 0


def run_alive() -> bool:
    # leading space distinguishes the run ("python comprehension.py") from this
    # poller ("python poll_comprehension.py", preceded by "_", not a space)
    r = subprocess.run(["pgrep", "-f", " comprehension.py"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def fmt_eta(seconds: float) -> str:
    if seconds <= 0 or seconds != seconds:  # nonpositive or NaN
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def snapshot(total: int, prev: int | None, dt: float) -> tuple[int, str]:
    cur = raw_count()
    alive = run_alive()
    pct = 100 * cur / total if total else 0
    bar_n = int(pct // 5)
    bar = "█" * bar_n + "·" * (20 - bar_n)
    rate_txt, eta_txt = "", ""
    if prev is not None and dt > 0 and cur > prev:
        rate = (cur - prev) / dt  # calls/sec since last tick
        rate_txt = f"  {rate * 60:.0f}/min"
        eta_txt = f"  eta {fmt_eta((total - cur) / rate)}"
    state = "done" if cur >= total else ("running" if alive else "STOPPED (incomplete)")
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {bar} {cur:5d}/{total} {pct:5.1f}%{rate_txt}{eta_txt}  [{state}]"
    return cur, line


def main() -> None:
    ap = argparse.ArgumentParser(description="poll P1 comprehension-run progress")
    ap.add_argument("--interval", type=int, default=90, help="seconds between polls (default 90)")
    ap.add_argument("--samples", type=int, default=2, help="samples per model used by the run (default 2)")
    ap.add_argument("--once", action="store_true", help="print one snapshot and exit")
    args = ap.parse_args()

    total = total_calls(args.samples)
    prev, prev_t = None, None
    while True:
        now = time.monotonic()
        dt = (now - prev_t) if prev_t else 0
        cur, line = snapshot(total, prev, dt)
        print(line, flush=True)
        prev, prev_t = cur, now
        if args.once or cur >= total:
            break
        if not run_alive() and cur < total:
            print("  run process not found and count below total — exiting.", flush=True)
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
