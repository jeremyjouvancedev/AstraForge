# AstraForge Toolkit

Lightweight Python package for using AstraForge DeepAgent and sandboxes from another project.

Contents:
- `astraforge_sandbox_backend.SandboxBackend`: DeepAgents backend that executes via the remote AstraForge sandbox API.
- `astraforge_sandbox_backend.DeepAgentClient`: HTTP client for DeepAgent conversations and streaming replies.

## Install

```bash
pip install astraforge-toolkit
```

## Quick start

### Create a sandbox-backed DeepAgent

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from astraforge_sandbox_backend import SandboxBackend

def backend_factory(rt):
    return SandboxBackend(
        rt,
        base_url="https://your.astra.forge/api",
        api_key="your-api-key",
        # optional: session_params={"image": "astraforge/codex-cli:latest"},
    )

model = ChatOpenAI(model="gpt-4o", api_key="...")
agent = create_deep_agent(model=model, backend=backend_factory)
```

### Call DeepAgent over HTTP

```python
from astraforge_sandbox_backend import DeepAgentClient

client = DeepAgentClient(base_url="https://your.astra.forge/api", api_key="your-api-key")
conv = client.create_conversation()

for chunk in client.stream_message(conv.conversation_id, "Hello, sandbox!"):
    print(chunk)
```

## Build & publish

```bash
cd astraforge-python-package
python -m build
python -m twine upload dist/*  # or use --repository testpypi
```

Configure `~/.pypirc` or set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<pypi-token>` for uploads.
