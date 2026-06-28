"""Console (CLI) definitions — scheduled tasks + closure commands (cf. Laravel's routes/console.php).

Loaded by the console kernel on every `arvel <command>` (not by the HTTP server).

Scheduled tasks — run by `arvel schedule:run` (point a once-a-minute cron at it):

    from arvel import Schedule

    Schedule.command("queue:work --stop-when-empty").hourly()
    Schedule.call(prune_old_exports).daily_at("02:00")

Closure commands (Laravel `Artisan::command`) — appear in `arvel --help` and run through the booted
app (handler args come from the CLI; everything else is autowired from the container):

    from arvel import Console

    async def greet(name: str):
        print(f"Hello, {name}!")

    Console.command("greet {name}", greet)   # $ arvel greet Ada  ->  Hello, Ada!

Signature tokens: `{arg}` (required), `{arg?}` (optional), `{--flag}` (boolean option). For larger
commands, prefer a class via `arvel make:command` (type-safe, DI-aware).
"""
