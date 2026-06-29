# Deployment

Production deployment uses `Dockerfile.prod`, `docker-compose.prod.yml`, PostgreSQL, Redis, Nginx TLS termination, Prometheus metrics, and health/readiness endpoints.

Required environment values:

- `JWT_SECRET`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `DATABASE_*`
- `REDIS_*`
- Broker credentials through `BROKER_<EXCHANGE>_API_KEY`, `BROKER_<EXCHANGE>_SECRET`, and optional `BROKER_<EXCHANGE>_PASSWORD`.

Run production stack:

```bash
docker compose -f docker-compose.prod.yml up --build
```

Nginx expects TLS material in `deployment/nginx/certs/fullchain.pem` and `deployment/nginx/certs/privkey.pem`.
