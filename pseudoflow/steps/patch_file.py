import asyncio

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import run_pod_and_get_logs, select_nodes


async def handle(step: dict, ctx: FlowContext) -> None:
    path = step.get("path")
    pattern = step.get("pattern")
    replace = step.get("replace", "")
    create = bool(step.get("createIfMissing", False))
    selector = step.get("nodeSelector") or {}

    if not path or not pattern:
        raise ValueError("patchFile.path and pattern required")

    nodes = select_nodes(ctx.apis, selector)
    loop = asyncio.get_event_loop()

    for node in nodes:
        sh = (
            f'if [ ! -f "/host{path}" ] && ' + ("true" if create else "false") +
            f'; then install -D -m 0644 /dev/null "/host{path}"; fi; '
            f'if [ -f "/host{path}" ]; then '
            f'sed -r -i "s/{pattern}/{replace}/g" "/host{path}"; fi;'
        )

        await loop.run_in_executor(
            None,
            run_pod_and_get_logs,
            ctx.apis,
            ctx.namespace or ctx.operator_ns,
            sh,
            {"kubernetes.io/hostname": node},
            True,
            [{"hostPath": "/", "mountPath": "/host"}],
            600,
        )
