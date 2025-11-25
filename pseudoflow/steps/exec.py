import asyncio

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import run_pod_and_get_logs


async def handle(step: dict, ctx: FlowContext) -> None:
    cmd = step.get("cmd")
    if not cmd:
        raise ValueError("exec.cmd required")

    tout = int(step.get("timeoutSeconds", 600))

    loop = asyncio.get_event_loop()
    out = await loop.run_in_executor(
        None,
        run_pod_and_get_logs,
        ctx.apis,
        ctx.namespace or ctx.operator_ns,
        cmd,
        None,
        False,
        None,
        tout,
    )

    var = step.get("var")
    if var:
        ctx.vars[var] = out
