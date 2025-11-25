import asyncio
from pseudoflow.engine.context import FlowContext


async def handle(step: dict, ctx: FlowContext) -> None:
    secs = int(step.get("seconds", 1))
    await asyncio.sleep(secs)
