import asyncio

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import run_pod_and_get_logs, select_nodes
from pseudoflow.util.shell import sh_quote


async def handle(step: dict, ctx: FlowContext) -> None:
    path = step.get("path")
    content = step.get("content", "")
    mode = step.get("mode", "0644")
    owner = step.get("owner", "root:root")
    selector = step.get("nodeSelector") or {}

    if not path:
        raise ValueError("configFile.path required")

    nodes = select_nodes(ctx.apis, selector)
    loop = asyncio.get_event_loop()

    for node in nodes:
        cmd = (
            f'install -D -m {mode} /dev/stdin "/host{path}" '
            f'&& chown {owner} "/host{path}"'
        )
        payload = f"echo -n {sh_quote(content)} | /bin/sh -lc {sh_quote(cmd)}"

        await loop.run_in_executor(
            None,
            run_pod_and_get_logs,
            ctx.apis,
            ctx.namespace or ctx.operator_ns,
            payload,
            {"kubernetes.io/hostname": node},
            True,
            [{"hostPath": "/", "mountPath": "/host"}],
            600,
        )
