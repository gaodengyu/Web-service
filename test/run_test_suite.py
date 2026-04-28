from __future__ import annotations

import io
import json
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "test" / "results"
TESTS_DIR = ROOT / "test" / "tests"


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    loader = unittest.defaultTestLoader
    suite = loader.discover(str(TESTS_DIR), top_level_dir=str(ROOT))

    buffer = io.StringIO()
    runner = unittest.TextTestRunner(stream=buffer, verbosity=2)

    started_at = time.time()
    result = runner.run(suite)
    duration_seconds = round(time.time() - started_at, 3)

    log_text = buffer.getvalue()
    summary = {
        "success": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(getattr(result, "skipped", [])),
        "duration_seconds": duration_seconds,
    }

    (RESULTS_DIR / "unittest_run.log").write_text(log_text, encoding="utf-8")
    (RESULTS_DIR / "unittest_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    sys.stdout.write(log_text)
    sys.stdout.write("\n")
    sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
