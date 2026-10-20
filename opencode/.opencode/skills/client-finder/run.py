"""Glue script for Opencode skill integration.

This script is invoked by the Opencode agent when it calls the
client-finder skill. It delegates to the client-finder CLI.
"""

from __future__ import annotations

import sys

from client_finder.cli import main


if __name__ == "__main__":
    sys.exit(main())