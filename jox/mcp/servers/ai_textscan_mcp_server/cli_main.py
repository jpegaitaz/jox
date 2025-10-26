# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import logging
from .server import create_app

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app = create_app()
    app.run_stdio()
