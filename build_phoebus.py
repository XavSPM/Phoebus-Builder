#!/usr/bin/env python3
"""
Convenience entry point for Phoebus Builder.
Delegates to phoebus_builder.cli.main.
"""

import sys
from phoebus_builder.cli import main

if __name__ == "__main__":
    sys.exit(main())
