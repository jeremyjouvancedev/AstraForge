"""Shared helpers for sampling container CPU usage from cgroup stats."""

from __future__ import annotations

from typing import Iterable, Sequence

CPU_CGROUP_PATHS: Sequence[str] = (
    "/sys/fs/cgroup/cpu.stat",
    "/sys/fs/cgroup/cpu/cpuacct.usage",
    "/sys/fs/cgroup/cpuacct/cpuacct.usage",
)


def build_cpu_probe_script(paths: Iterable[str] | None = None) -> str:
    """Return a shell snippet that prints the first cgroup file that exists."""

    candidates = list(paths or CPU_CGROUP_PATHS)
    path_list = " ".join(candidates)
    return (
        "for path in "
        f"{path_list} "
        '; do if [ -f "$path" ]; then echo "__PATH:$path__"; cat "$path"; exit 0; fi; '
        "done; exit 1"
    )


def parse_cpu_usage_payload(payload: str | None) -> float | None:
    """Parse the stdout emitted by ``build_cpu_probe_script`` into seconds."""

    if not payload:
        return None
    lines = [line.strip() for line in payload.strip().splitlines() if line.strip()]
    if not lines:
        return None
    path_hint: str | None = None
    if lines[0].startswith("__PATH:") and lines[0].endswith("__"):
        path_hint = lines[0][len("__PATH:") : -2]
        lines = lines[1:]
    body = "\n".join(lines).strip()
    if not body:
        return None
    if path_hint and path_hint.endswith("cpu.stat"):
        usage_usec = None
        for line in body.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in {"usage_usec", "usage_us"}:
                try:
                    usage_usec = float(parts[1])
                    break
                except ValueError:
                    continue
        if usage_usec is not None:
            return max(0.0, usage_usec / 1_000_000)
    stripped = body.splitlines()[0].strip()
    try:
        nanoseconds = float(stripped)
        return max(0.0, nanoseconds / 1_000_000_000)
    except ValueError:
        return None
