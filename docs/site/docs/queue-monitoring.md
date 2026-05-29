# Queue Monitoring

Arvel doesn't ship a first-party queue dashboard, but gives you the CLI tools you need and plays well with off-the-shelf monitoring.

## Built-in CLI

```bash
arvel queue:work                  # start a worker
arvel queue:work --queue high,low # process named queues in priority order
arvel queue:failed                # list failed jobs
arvel queue:retry <id>            # retry a specific failed job
arvel queue:flush                 # clear the failed-jobs table
```

## Metrics

Arvel workers emit structured log lines for every job processed. Route those logs to your observability stack:

```python
import structlog

log = structlog.get_logger()
log.info("job.processed", job=job_class, duration_ms=elapsed, queue=queue_name)
```

For Redis-backed queues, **RQ Dashboard** gives you a simple web UI:

```bash
uv add rq[dashboard]
rq-dashboard --redis-url redis://localhost:6379
```

For AMQP (RabbitMQ), the RabbitMQ Management UI is available at `http://localhost:15672` when you run the `management`-tagged image.

## See also

- [Queues](queues.md) — full queue configuration, drivers, and job authoring.
- [Task Scheduling](scheduling.md) — running recurring jobs.
