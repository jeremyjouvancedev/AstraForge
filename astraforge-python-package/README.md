# AstraForge Toolkit

Lightweight Python package for using AstraForge DeepAgent and sandboxes from another project.

Contents:
- `astraforge_toolkit.SandboxBackend`: DeepAgents backend that executes via the remote AstraForge sandbox API.
- `astraforge_toolkit.DeepAgentClient`: HTTP client for DeepAgent conversations and streaming replies.
- Remote sandbox tools: `sandbox_shell`, `sandbox_python_repl`, `sandbox_open_url_with_playwright`,
  `sandbox_view_image` — all execute inside the sandbox via HTTP.

## Install

```bash
pip install astraforge-toolkit
```

## Quick start

### Create a sandbox-backed DeepAgent

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from astraforge_toolkit import (
    SandboxBackend,
    sandbox_shell,
    sandbox_python_repl,
    sandbox_open_url_with_playwright,
    sandbox_view_image,
)

def backend_factory(rt):
    return SandboxBackend(
        rt,
        base_url="https://your.astra.forge/api",
        api_key="your-api-key",
        # optional: session_params={"image": "astraforge/codex-cli:latest"},
    )

model = ChatOpenAI(model="gpt-4o", api_key="...")
agent = create_deep_agent(model=model, backend=backend_factory)

# Optional: register sandbox tools with your agent/tool registry
tools = [sandbox_shell, sandbox_python_repl, sandbox_open_url_with_playwright, sandbox_view_image]
```

### Call DeepAgent over HTTP

```python
from astraforge_toolkit import DeepAgentClient

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

## Examples

See `examples/local_api_test.ipynb` for a quick notebook that exercises the client against a local
`http://localhost:8000/api` instance.
