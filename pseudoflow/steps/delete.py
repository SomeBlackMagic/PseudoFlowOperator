import asyncio

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import delete_target


async def handle(step: dict, ctx: FlowContext) -> None:
    target = step.get("target")
    if not target:
        raise ValueError("delete.target required")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, delete_target, ctx.apis, target, ctx.namespace)
