"""Allow running the package with ``python -m preprint_radar``."""

import sys

from preprint_radar.cli import main

if __name__ == "__main__":
    sys.exit(main())
