import logging
from pseudoflow.engine.context import FlowContext

logger = logging.getLogger("pseudoflow.step.log")


async def handle(step: dict, ctx: FlowContext) -> None:
    msg = step.get("message", "")
    logger.info("[log] %s", msg)
