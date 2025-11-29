# AstraForge Sandbox Backend client

This package provides:

- a `SandboxBackend` implementation for `deepagents` so you can build your own
  DeepAgent graphs while executing all filesystem/shell operations inside an
  AstraForge sandbox, and
- a small synchronous HTTP client for the built-in `/api/deepagent/...` endpoints.

## Use as a DeepAgents backend

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from astraforge_sandbox_backend import SandboxBackend


def backend_factory(rt):
    # Point this at your AstraForge API (`/api` root) and API key.
    return SandboxBackend(
        rt,
        base_url="https://your-astra-instance.example.com/api",
        api_key="your-api-key-here",
        # optional: control the sandbox session (image, mode, limits, etc.)
        # session_params={
        #     "mode": "docker",
        #     "image": "astraforge/codex-cli:latest",
        #     "idle_timeout_sec": 900,
        #     "max_lifetime_sec": 3600,
        # },
    )


model = ChatOpenAI(model="gpt-4o", api_key="sk-...")
agent = create_deep_agent(model=model, backend=backend_factory)

# Now any filesystem / shell tools configured in your DeepAgent
# will run inside an AstraForge sandbox container.
result = agent.invoke(
    {"messages": [{"role": "user", "content": "List files in the workspace"}]}
)
print(result)
```

To talk to a locally running AstraForge instance, point `base_url` at
`http://localhost:8000/api` and use an API key generated from the AstraForge UI.

If you prefer, you can also pass an existing sandbox session id via the DeepAgents
runtime config:

```python
config = {
    "thread_id": "my-thread",
    "configurable": {"sandbox_session_id": "existing-session-uuid"},
}
agent.invoke({"messages": [...]}, config=config)
```

In that case the backend will reuse your pre-provisioned sandbox.

## Use the high-level DeepAgent HTTP client

```python
from astraforge_sandbox_backend import DeepAgentClient

client = DeepAgentClient(
    base_url="https://your-astra-instance.example.com/api",
    api_key="your-api-key-here",
)

conversation = client.create_conversation()

for chunk in client.stream_message(
    conversation_id=conversation["conversation_id"],
    content="Refactor my project to use feature flags.",
):
    # Each chunk is a dict containing tokens/messages/tool_events, similar to the AstraForge UI.
    print(chunk.get("tokens") or chunk.get("messages"))
```
