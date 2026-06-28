"""The application bootstrap — the one place that configures and builds the app.

Both the CLI (`arvel <command>`) and the ASGI entrypoint (`asgi.py`) load the app from here via
`create_app()`. Configure routing, providers, middleware, and the config directory below.
"""

from pathlib import Path

from arvel.kernel import Application

# The project root (this file lives in bootstrap/), resolved from __file__ so it's correct no
# matter the current working directory.
BASE_PATH = Path(__file__).resolve().parent.parent


def create_app() -> Application:
    return (
        Application.configure(str(BASE_PATH))
        .with_config_dir(BASE_PATH / "config")
        .with_providers(BASE_PATH / "bootstrap" / "providers.py")
        .with_middlewares(BASE_PATH / "bootstrap" / "middlewares.py")
        .with_routing(
            web=BASE_PATH / "routes" / "web.py",  # stateful browser routes (the "web" group)
            api=BASE_PATH / "routes" / "api.py",  # stateless JSON routes ("api" group, /api prefix)
            console=BASE_PATH / "routes" / "console.py",  # CLI command definitions
        )
        .create()
    )
