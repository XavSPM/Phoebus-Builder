"""
Entry point for running Phoebus Builder as a module (python -m phoebus_builder).
"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
