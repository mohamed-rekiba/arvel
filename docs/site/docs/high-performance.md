# High-Performance Runtime

Arvel is async-native and runs on any ASGI server with no extra packages. Uvicorn is the default; swap it for **Granian** or **Hypercorn** for higher throughput:

```bash
uv add granian
granian --interface asgi app:create_app --factory --workers 4
```

Granian uses Rust's Tokio runtime and typically outperforms Uvicorn on CPU-bound workloads. For I/O-bound APIs, Uvicorn with `--workers $(nproc)` is already fast.

## See also

- [Deployment](deployment.md) — production server configuration.
