# Local Kubernetes Runbook

Use the Kubernetes manifests under `infra/k8s/local` whenever you want to run the
full AstraForge stack inside a local cluster (Kind, k3d, Minikube, or another
single-node engine). This lets you validate the Kubernetes provisioner and
runtime configuration in parallel with the existing Docker Compose workflow.

## Prerequisites

- Docker Engine (so you can build the backend, worker, frontend, and proxy images)
- `kubectl` 1.27+ and a local cluster (examples below use [Kind](https://kind.sigs.k8s.io/))
- Access to an OpenAI-compatible API key for the LLM proxy
- Ports `5173`, `8000`, and `8080` free on your workstation for port-forwarding

## 1. Create (or reuse) a local cluster

Kind example:

```bash
kind create cluster --name astraforge
```

If you are using k3d/Minikube, ensure the default storage class is available so
the Postgres deployment can request an `emptyDir` volume.

## 2. Build the images for Kubernetes

Build the same containers Compose uses, plus the Codex workspace image that the
provisioner spawns, and tag them for local use:

```bash
docker build -t astraforge/backend:local backend
# worker uses the backend image
docker build -t astraforge/frontend:local frontend
docker build -t astraforge/llm-proxy:local llm-proxy
docker build -t astraforge/codex-cli:latest backend/codex_cli_stub
```

When using Kind, load the freshly built images into the cluster so Kubernetes
can pull them without contacting a registry:

```bash
kind load docker-image astraforge/backend:local --name astraforge
kind load docker-image astraforge/frontend:local --name astraforge
kind load docker-image astraforge/llm-proxy:local --name astraforge
kind load docker-image astraforge/codex-cli:latest --name astraforge
```

(With k3d or Minikube you can either load the images similarly or push them to a
registry that the cluster can reach.)

## 3. Bootstrap the namespace and secrets

Create the namespace once:

```bash
kubectl apply -f infra/k8s/local/namespace.yaml
```

Add your LLM credentials as a secret (rerunnable via `kubectl apply`):

```bash
kubectl -n astraforge-local create secret generic astraforge-llm \
  --from-literal=OPENAI_API_KEY=sk-... \
  --dry-run=client -o yaml | kubectl apply -f -
```

The backend, worker, and proxy pods read their local-safe defaults from the
`astraforge-backend-env` and `astraforge-frontend-env` ConfigMaps, so most of the
usual `.env` variables are not required here. Update those ConfigMaps if you need
different log levels or URLs.

## 4. Deploy the stack

Apply everything with kustomize:

```bash
kubectl apply -k infra/k8s/local
```

The backend deployment runs migrations as an init container before the API pod
starts up, so no manual migration job is required. Watch the pods come online:

```bash
kubectl get pods -n astraforge-local
kubectl logs deployment/backend -n astraforge-local -f
```

The overlay creates the `astraforge-operator` service account plus the RBAC
permissions required for the backend and Celery worker pods to create/exec into
Codex workspace pods.

## 5. Expose services for local testing

The manifests leave services as `ClusterIP` so they are isolated by default. Use
port-forwarding when you want to drive the UI from your browser:

```bash
# Terminal 1 – backend API and SSE
kubectl port-forward svc/backend 8000:8000 -n astraforge-local

# Terminal 2 – frontend Vite dev server
kubectl port-forward svc/frontend 5173:5173 -n astraforge-local

# Optional – LLM proxy, if you want to call it directly
kubectl port-forward svc/llm-proxy 8080:8080 -n astraforge-local
```

Visit http://localhost:5173 to use the UI; it proxies API calls back to the
backend service via the forwarded port at http://localhost:8000.

## 6. Tear down

Clean up the namespace when you are done testing:

```bash
kubectl delete namespace astraforge-local
```

The Docker images remain cached locally, so redeploying later only requires
re-loading them into your cluster.

## Troubleshooting

- **Pods stuck in `ImagePullBackOff`** – re-run the `kind load docker-image ...`
  commands (or push to a registry) so the cluster can access the `:local` tags.
- **LLM proxy fails to start** – confirm the `astraforge-llm` secret contains a
  valid `OPENAI_API_KEY`.
- **Frontend cannot reach the backend** – make sure both `kubectl port-forward`
  commands are running; the SPA calls `http://localhost:8000` by design.
- **Database reset between restarts** – the Postgres deployment uses `emptyDir`
  for fast feedback. For persistent volumes swap that block with a PVC in
  `infra/k8s/local/postgres.yaml`.

With these manifests you can iterate on Kubernetes changes locally while the
Docker Compose workflow remains available for quick single-machine setups.
