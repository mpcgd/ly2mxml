"""Run the package as ``python -m ly2mxml``.

The module delegates directly to the CLI entry point so the package behaves
the same whether it is launched through the installed ``ly2mxml`` script or
through Python's module execution mode.
"""

from ly2mxml.cli import main


raise SystemExit(main())
