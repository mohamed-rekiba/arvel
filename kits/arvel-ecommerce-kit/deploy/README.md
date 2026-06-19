# Production container images

Build from the **monorepo root** (`repos/arvel`), not from this directory.

```bash
cd /path/to/arvel

docker build \
  -f kits/arvel-ecommerce-kit/deploy/Dockerfile \
  --target app \
  -t docker.io/rekiba/ecommerce-app:local \
  .

docker build \
  -f kits/arvel-ecommerce-kit/deploy/Dockerfile \
  --target scheduler \
  -t docker.io/rekiba/ecommerce-scheduler:local \
  .
```

Release flow:

1. Tag `arvel-ecommerce-kit-v<semver>` on the arvel repo.
2. GHA workflow `.github/workflows/ecommerce-images.yml` pushes both images to Docker Hub.
3. The same workflow opens a PR on `homelab-gitops` to bump image tags → merge → Argo CD sync.

### Observability (Kubernetes)

The homelab-gitops chart sets OTEL + Prometheus env vars. The app exposes `/_metrics`
when `OBSERVABILITY_METRICS_ENABLED=true` (wired by the chart). Rebuild images after
framework changes in `packages/arvel`.

Local runtime expects env vars from OpenBao/ESO in cluster; for smoke tests, mirror
`docker-compose.yml` env and run migrations with `arvel migrate` before `arvel serve`.
