"""Package entrypoint that executes the full CLI in this module namespace."""

from pathlib import Path

_APP_PATH = Path(__file__).with_name("app.py")
exec(compile(_APP_PATH.read_text(), str(_APP_PATH), "exec"), globals())
