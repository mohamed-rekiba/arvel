# Docker Dev Environment

The `arvel new` starter kit ships a `docker-compose.yml` that provisions every dependency your app needs locally: the Arvel app, Postgres, Redis, and optional extras (RabbitMQ, MinIO, Mailpit, Reverb).

## Starting the stack

```bash
arvel new my-app
cd my-app
make up          # docker compose up -d
make migrate     # run migrations inside the container
make seed        # seed the database
```

The app is available at `http://localhost:8000` by default. `make logs` tails all container output; `make down` stops everything.

## Adding services

Open `docker-compose.yml` and add any service you need. Here's a minimal RabbitMQ entry:

```yaml
rabbitmq:
  image: rabbitmq:4-management-alpine
  ports:
    - "5672:5672"
    - "15672:15672"
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]
    interval: 10s
    retries: 5
```

Then update `QUEUE_DRIVER=amqp` and `AMQP_URL=amqp://guest:guest@rabbitmq/` in your `.env`.

## Running commands inside the container

```bash
make shell.backend    # bash in the app container
make cli CMD="migrate:fresh --seed"
```

## See also

- [Installation](installation.md) — full `arvel new` walkthrough.
- [Deployment](deployment.md) — production container patterns.
- [Deployment](deployment.md) — production container setup.
