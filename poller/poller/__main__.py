"""Module-level CLI entry — `python -m poller` runs one poll cycle and exits.

Spec § 2.1 calls for a one-shot process driven by an external scheduler (cron,
Azure Function timer, GitHub Actions). This module is the canonical entry; the
older `python -m poller.scheduler` form still works for backward compatibility.
"""

from __future__ import annotations

import sys

from poller.scheduler import cli_main

if __name__ == "__main__":
    sys.exit(cli_main(sys.argv[1:]))
