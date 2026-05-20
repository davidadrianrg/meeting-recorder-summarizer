"""Entry point para ejecutar meeting_recorder como módulo.

Uso: python -m meeting_recorder [comando]
Comandos: toggle, status, serve
"""

import sys
from meeting_recorder.cli import main

if __name__ == "__main__":
    sys.exit(main())
