from .client import (
    DeepAgentClient,
    DeepAgentConversation,
    DeepAgentError,
    SandboxArtifact,
    SandboxSession,
)

__all__ = [
    "SandboxBackend",
    "DeepAgentClient",
    "DeepAgentConversation",
    "DeepAgentError",
    "SandboxArtifact",
    "SandboxSession",
    "sandbox_shell",
    "sandbox_python_repl",
    "sandbox_open_url_with_playwright",
    "sandbox_view_image",
]


def __getattr__(name: str):
    if name == "SandboxBackend":
        try:
            from .backend import SandboxBackend  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise ImportError("SandboxBackend requires optional deepagents/langchain deps") from exc
        globals()["SandboxBackend"] = SandboxBackend
        return SandboxBackend

    if name in {
        "sandbox_shell",
        "sandbox_python_repl",
        "sandbox_open_url_with_playwright",
        "sandbox_view_image",
    }:
        try:
            from .tools import (  # type: ignore
                sandbox_shell,
                sandbox_python_repl,
                sandbox_open_url_with_playwright,
                sandbox_view_image,
            )
        except Exception as exc:  # noqa: BLE001
            raise ImportError("Sandbox LangChain tools require optional dependencies") from exc
        globals().update(
            {
                "sandbox_shell": sandbox_shell,
                "sandbox_python_repl": sandbox_python_repl,
                "sandbox_open_url_with_playwright": sandbox_open_url_with_playwright,
                "sandbox_view_image": sandbox_view_image,
            }
        )
        return globals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
