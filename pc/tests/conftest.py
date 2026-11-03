"""Permite importar los módulos de pc/ al correr pytest desde cualquier carpeta."""

import sys
from pathlib import Path

PC_DIR = Path(__file__).resolve().parents[1]
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))
