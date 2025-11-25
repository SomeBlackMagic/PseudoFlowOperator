import asyncio
from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import wait_for_resource_condition


async def handle(step: dict, ctx: FlowContext) -> None:
    res = step.get("resource", {})
    cond = step.get("condition", "Exist")
    tout = int(step.get("timeoutSeconds", 300))
    interval = int(step.get("intervalSeconds", 5))
    jp = step.get("jsonPath")
    op = step.get("op")
    val = step.get("value")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        wait_for_resource_condition,
        ctx.apis,
        res,
        cond,
        tout,
        interval,
        ctx.namespace,
        jp,
        op,
        val,
    )
