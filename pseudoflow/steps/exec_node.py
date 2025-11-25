import asyncio
import json

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import run_pod_and_get_logs, select_nodes


async def handle(step: dict, ctx: FlowContext) -> None:
    cmd = step.get("cmd")
    if not cmd:
        raise ValueError("execNode.cmd required")

    selector = step.get("nodeSelector") or {}
    run_on = step.get("runOn", "any")  # any|first|all
    var_per = step.get("varPerNode")
    timeout = int(step.get("timeoutSeconds", 600))

    nodes = select_nodes(ctx.apis, selector)
    if not nodes:
        return

    if run_on == "first":
        targets = [nodes[0]]
    elif run_on == "any":
        targets = [nodes[0]]
    else:
        targets = nodes

    loop = asyncio.get_event_loop()
    outputs = {}

    for node in targets:
        out = await loop.run_in_executor(
            None,
            run_pod_and_get_logs,
            ctx.apis,
            ctx.namespace or ctx.operator_ns,
            cmd,
            {"kubernetes.io/hostname": node},
            True,
            None,
            timeout,
        )
        outputs[node] = out

    if var_per:
        ctx.vars[var_per] = json.dumps(outputs)
