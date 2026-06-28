#!/usr/bin/env bash
# E2E consumer smoke — the gate that "green unit tests" cannot satisfy.
#
# Consumes arvel exactly as an end user does: scaffold a fresh app with the CLI, confirm the project is
# recognized, run an app-dependent command, then boot the served app and hit an endpoint. This is the
# executable acceptance test for the consumer/scaffold/serve path (the path that shipped broken under a
# fully-green unit suite). Run by CI (.github/workflows/ci.yml :: e2e) and reusable locally:
#   uv run bash tools/e2e_smoke.sh
set -euo pipefail

arvel() { python -m arvel.console "$@"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "== 1. scaffold a fresh app =="
arvel new blog
cd blog

# NB: capture output into a var, then match — never `arvel … | grep -q …`. With `set -o pipefail`,
# grep -q closes the pipe on first match and the producer dies with SIGPIPE (141), which pipefail
# reports as a failure even though the match succeeded.
echo "== 2. the fresh project is recognized (project commands visible) =="
# `migrate` is a project-only command (hidden in installer mode) whose displayed name == its invocation,
# so it's a stable "recognized as a project?" signal (the colon commands display hyphenated — D7).
help_out="$(arvel --help)"
case "$help_out" in
  *migrate*) ;;
  *) echo "FAIL: a freshly-scaffolded project is not recognized — project commands hidden (CLI-2/D1)"; exit 1 ;;
esac

echo "== 3. an app-dependent command boots the app and works =="
routes_out="$(arvel route:list)"
case "$routes_out" in
  *home*) ;;  # the scaffolded home route (GET / -> home) is registered + listed
  *) echo "FAIL: 'route:list' did not list the scaffolded '/' route (D1)"; printf '%s\n' "$routes_out"; exit 1 ;;
esac

# vendor:publish boots the app + reads app.published through the real CLI path. The framework ships
# publishable default lang files (validation/pagination), so a fresh project publishes them — Laravel
# lang:publish equivalent (`vendor:publish --tag=lang`).
publish_out="$(arvel vendor:publish)"
case "$publish_out" in
  *"published"*) echo "   vendor:publish runs via the CLI (publishes the framework lang defaults)" ;;
  *) echo "FAIL: 'vendor:publish' did not run cleanly in a fresh project"; printf '%s\n' "$publish_out"; exit 1 ;;
esac

echo "== 4. the served app actually serves its scaffolded route =="
python - <<'PY'
import sys
sys.path.insert(0, ".")
from litestar.testing import TestClient
from asgi import asgi_app

with TestClient(app=asgi_app) as client:
    resp = client.get("/")
    assert resp.status_code == 200, f"GET / -> {resp.status_code} (expected 200) — scaffolded web route not served (D2)"
    # home renders resources/views/welcome.html via `from arvel import view` — the documented flow.
    # (This is the exact path that regressed when the `view` helper collided with the arvel.views module.)
    ctype = resp.headers.get("content-type", "")
    assert "text/html" in ctype, f"GET / content-type {ctype!r} — welcome view not rendered as HTML"
    assert "<h1>" in resp.text and "arvel app is running" in resp.text, "welcome view did not render"
    # the fluent bootstrap's api group is URL-prefixed /api: routes/api.py's /health -> /api/health
    api = client.get("/api/health")
    assert api.status_code == 200, f"GET /api/health -> {api.status_code} (expected 200) — api group/prefix not applied"
print("   GET / -> 200 (welcome view rendered via `from arvel import view`) ; GET /api/health -> 200")
PY

echo "== 5. the shell boots, autoloads the app + models, and supports top-level await =="
arvel make:model Widget >/dev/null
# `|| true`: don't let pipefail abort the capture (the stdlib fallback REPL exits 1 on EOF) before the
# case below can render a useful diagnostic.
shell_out="$(printf 'print("SHELL", Widget.__name__, type(app).__name__, await __import__("asyncio").sleep(0, 7))\nexit\n' | arvel shell 2>&1)" || true
case "$shell_out" in
  *"SHELL Widget Application 7"*) ;;  # model autoloaded by name + app loaded + top-level await works
  *) echo "FAIL: shell didn't autoload model/app or top-level await failed"; printf '%s\n' "$shell_out"; exit 1 ;;
esac
echo "   shell: Widget + app autoloaded, await OK"

echo "== 6. the scaffolded app's own test suite passes (pytest) =="
test_out="$(python -m pytest -q 2>&1)" || { echo "FAIL: scaffolded app's pytest failed"; printf '%s\n' "$test_out"; exit 1; }
case "$test_out" in
  *passed*) ;;
  *) echo "FAIL: scaffolded app's pytest reported no passing tests"; printf '%s\n' "$test_out"; exit 1 ;;
esac
echo "   app pytest: passed"

echo "== 7. migrations + seeder run via the CLI (the real DB path) =="
# the 4 scaffolded migrations are discovered by convention (database/migrations) and applied;
# the seeder is bound by AppServiceProvider so db:seed runs.
mig_out="$(arvel migrate 2>&1)"
case "$mig_out" in
  *"migrated 4 migration"*) ;;
  *) echo "FAIL: 'arvel migrate' did not apply the 4 scaffolded migrations"; printf '%s\n' "$mig_out"; exit 1 ;;
esac
seed_out="$(arvel db:seed 2>&1)" || { echo "FAIL: 'arvel db:seed' errored"; printf '%s\n' "$seed_out"; exit 1; }
case "$seed_out" in
  *"no seeder bound"*) echo "FAIL: db:seed found no bound seeder"; printf '%s\n' "$seed_out"; exit 1 ;;
esac
echo "   migrate: 4 migrations applied; db:seed: ran"

# Laravel parity: the users table carries email_verified_at, and the user can be marked verified so the
# `verified` route middleware works (it reads email_verified_at). Exercised on the real migrated DB.
python - <<'PY'
import asyncio, sys
sys.path.insert(0, ".")
from bootstrap.app import create_app
from arvel.kernel.bootstrap import bootstrap_app
from app.models.user import User
from arvel.auth import current_user
from arvel.auth.middleware import EnsureEmailVerified
from arvel.http.exceptions import HttpException

async def _call_next(_req):
    return "OK"

async def main():
    app = create_app(); bootstrap_app(app); await app.boot()
    assert "email_verified_at" in User.__table__.columns, "users model has no email_verified_at column"
    user = await User.create(name="EV", email="ev@example.com", password="pw")
    token = current_user.set(user)
    try:
        try:
            await EnsureEmailVerified().handle(object(), _call_next)
            raise SystemExit("FAIL: unverified user passed the 'verified' middleware")
        except HttpException:
            pass  # 403 as expected
        assert await user.mark_email_as_verified() is True
        assert await EnsureEmailVerified().handle(object(), _call_next) == "OK", "verified user blocked"
    finally:
        current_user.reset(token)

asyncio.run(main())
print("   email verification: users.email_verified_at present; mark_email_as_verified() unlocks 'verified' middleware")
PY

echo "== 7b. a provider/app command class appears in --help and runs (CLI-3) =="
mkdir -p app/commands
cat > app/commands/greet.py <<'PYCMD'
from arvel.console import Command


class GreetCommand(Command):
    signature = "greet"
    description = "A custom app command."

    async def handle(self) -> None:
        self.info("GREET-OK")
PYCMD
cat > app/providers/app_provider.py <<'PYPROV'
from arvel.kernel import ServiceProvider


class AppServiceProvider(ServiceProvider):
    def register(self) -> None:
        from app.commands.greet import GreetCommand
        from database.seeders.database_seeder import DatabaseSeeder

        self.commands(GreetCommand)
        self.app.singleton("seeder", lambda _app: DatabaseSeeder())

    def boot(self) -> None: ...
PYPROV
help_out="$(arvel --help)"
case "$help_out" in
  *greet*) ;;
  *) echo "FAIL: a registered command class did not appear in --help (CLI-3)"; printf '%s\n' "$help_out"; exit 1 ;;
esac
greet_out="$(arvel greet 2>&1)"
case "$greet_out" in
  *GREET-OK*) ;;
  *) echo "FAIL: the registered command class did not run (CLI-3)"; printf '%s\n' "$greet_out"; exit 1 ;;
esac
echo "   CLI-3: 'greet' appears in --help and runs"

# best-effort discovery: a broken command module must not crash --help (it still lists built-ins).
mv app/commands/greet.py app/commands/greet.py.bak
echo "import a_module_that_does_not_exist_xyz  # noqa" > app/commands/greet.py
broken_help="$(arvel --help 2>&1)" || { echo "FAIL: --help crashed on a broken project (best-effort discovery)"; printf '%s\n' "$broken_help"; exit 1; }
case "$broken_help" in
  *migrate*) ;;  # built-ins still listed despite the broken command module
  *) echo "FAIL: --help did not list built-ins on a broken project"; printf '%s\n' "$broken_help"; exit 1 ;;
esac
mv app/commands/greet.py.bak app/commands/greet.py  # restore so later stages boot cleanly
echo "   CLI-3 best-effort: --help survives a broken command module"

echo "== 7c. schedule:run runs a task defined in routes/console.py (the real CLI path) =="
# define an always-due task; the console kernel loads routes/console.py on boot, so schedule:run sees it
cat >> routes/console.py <<'PYEOF'
from arvel import Schedule  # noqa: E402

Schedule.call(lambda: None).every_minute()
PYEOF
sched_out="$(arvel schedule:run)"
case "$sched_out" in
  *"ran 1 due task"*) echo "   schedule:run executed the due task from routes/console.py" ;;
  *) echo "FAIL: 'schedule:run' did not run the routes/console.py task"; printf '%s\n' "$sched_out"; exit 1 ;;
esac

echo "== 7d. a closure command (Console.command) appears in --help and runs (the real CLI path) =="
cat >> routes/console.py <<'PYEOF'
from arvel import Console  # noqa: E402


async def hello(name: str):
    print(f"HELLO:{name}")


async def ping(name: str = "world"):
    print(f"PING:{name}")


Console.command("hello {name}", hello)
Console.command("ping {name?}", ping)
PYEOF
help_out="$(arvel --help 2>&1)"
case "$help_out" in
  *hello*) ;;  # the closure command is discovered into --help
  *) echo "FAIL: closure command 'hello' not listed in --help"; printf '%s\n' "$help_out"; exit 1 ;;
esac
hello_out="$(arvel hello Ada 2>&1)"
case "$hello_out" in
  *HELLO:Ada*) ;;  # required-arg closure runs
  *) echo "FAIL: closure command 'hello Ada' did not run"; printf '%s\n' "$hello_out"; exit 1 ;;
esac
# a missing required arg renders a clean usage error (exit 2), not a traceback (|| guards set -e)
hello_code=0; arvel hello >/dev/null 2>&1 || hello_code=$?
[ "$hello_code" = "2" ] || { echo "FAIL: 'arvel hello' (missing arg) exited $hello_code, want 2 (usage error)"; exit 1; }
# an optional positional {name?} accepts a value AND falls back to the handler default when omitted
ping_val="$(arvel ping Bob 2>&1)";  case "$ping_val" in *PING:Bob*) ;; *) echo "FAIL: 'arvel ping Bob' (optional positional w/ value)"; printf '%s\n' "$ping_val"; exit 1 ;; esac
ping_def="$(arvel ping 2>&1)";      case "$ping_def" in *PING:world*) ;; *) echo "FAIL: 'arvel ping' (optional omitted → default)"; printf '%s\n' "$ping_def"; exit 1 ;; esac
echo "   closure commands: 'hello Ada' runs, 'hello' (no arg) → exit 2, 'ping Bob'/'ping' optional positional OK"

echo "== 8. OpenAPI schema is served, configured, and has request/response models =="
python - <<'PY'
import sys
sys.path.insert(0, ".")
from litestar.testing import TestClient
from asgi import asgi_app

with TestClient(app=asgi_app) as client:
    s = client.get("/schema/openapi.json")
    assert s.status_code == 200, "OpenAPI schema not served at /schema/openapi.json (config 'path')"
    doc = s.json()
    # title comes from typed OpenApiSettings (config/openapi.py), not Litestar's 'Litestar API' default
    assert doc["info"]["title"] != "Litestar API", f"OpenAPI title not configured: {doc['info']}"
    schemas = doc.get("components", {}).get("schemas", {})
    # the scaffolded typed routes generate request + response schemas
    assert {"EchoIn", "EchoOut", "HealthStatus"} <= set(schemas), f"missing request/response schemas: {list(schemas)}"
    echo = client.post("/api/echo", json={"message": "hi"})
    assert echo.status_code == 201 and echo.json() == {"echo": "hi"}, f"typed body route failed: {echo.status_code}"
print(f"   OpenAPI: title={doc['info']['title']!r}, schemas={sorted(schemas)}; POST /api/echo typed body OK")
PY

echo "== 9. --auth scaffold: the bearer flow works (login -> token -> protected route) =="
cd "$WORK"
arvel new secured --auth >/dev/null
cd secured
auth_out="$(python -m pytest -q tests/test_auth.py 2>&1)" || { echo "FAIL: --auth scaffold's auth tests failed"; printf '%s\n' "$auth_out"; exit 1; }
case "$auth_out" in
  *passed*) ;;
  *) echo "FAIL: --auth scaffold auth tests did not pass"; printf '%s\n' "$auth_out"; exit 1 ;;
esac
echo "   --auth: login issues a token, protected route enforces it"

# the --auth OpenAPI doc declares the bearer scheme (Authorize button) + marks the protected route
python - <<'PY'
import sys
sys.path.insert(0, ".")
from litestar.testing import TestClient
from asgi import asgi_app

with TestClient(app=asgi_app) as client:
    doc = client.get("/schema/openapi.json").json()
    scheme = doc.get("components", {}).get("securitySchemes", {}).get("bearerAuth")
    assert scheme and scheme["scheme"] == "bearer", f"bearer scheme missing: {doc.get('components')}"
    assert doc["paths"]["/api/user"]["get"].get("security") == [{"bearerAuth": []}], "protected route not marked secured"
    assert doc["paths"]["/api/login"]["post"].get("security") is None, "public login wrongly marked secured"
    # the --auth handlers are typed (arvel.Schema) → request/response schemas generate (not just default scaffold)
    schemas = doc.get("components", {}).get("schemas", {})
    assert {"Credentials", "UserOut"} <= set(schemas), f"--auth request/response schemas missing: {list(schemas)}"
    assert doc["paths"]["/api/login"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("Credentials"), "login request schema missing"
    # a login with no/invalid body is a clean 400 (typed body validation), not a 500 AttributeError
    assert client.post("/api/login").status_code == 400, "empty-body login should be 400 (was 500 None.get)"
    assert client.post("/api/login", json={"email": "x"}).status_code == 400, "missing-field login should be 400"
print("   --auth OpenAPI: bearer scheme + Credentials/UserOut schemas; empty-body login -> 400 (not 500)")
PY

echo "== E2E smoke: PASS — scaffold (default + --auth) is recognized, serves web+api routes, shell works, tests pass, migrations+seeder run, scheduler runs due tasks, OpenAPI served, bearer auth enforced =="
