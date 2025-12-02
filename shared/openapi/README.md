# OpenAPI Schema

The backend publishes an OpenAPI 3.1 schema at `/api/schema/`. Generate client packages for
frontend consumers with:

```bash
pnpm openapi --input http://localhost:8001/api/schema/ --output src/lib/generated
```

For typed Python clients, use `openapi-python-client`:

```bash
openapi-python-client generate --url http://localhost:8001/api/schema/
```
