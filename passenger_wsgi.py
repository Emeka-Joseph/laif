"""Loader for cPanel's Passenger.

Passenger imports this file and serves the callable named ``application``.
The application itself lives in ``app.py``: cPanel regenerates a stub over
this file whenever the Python App settings change, so keeping the real code
in a separate module means an overwrite cannot destroy it.

If cPanel does replace this file, its stub loads whatever name is in the
"Application startup file" box. That box must therefore say ``app.py`` and
never ``passenger_wsgi.py`` — a stub pointing at itself loads itself until
Python raises RecursionError.
"""

import os
import sys

# Passenger does not guarantee the application root is importable.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import application  # noqa: E402,F401
