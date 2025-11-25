import asyncio
import yaml
from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import apply_manifest_docs


async def handle(step: dict, ctx: FlowContext) -> None:
    path = step.get("path")
    if not path:
        raise ValueError("applyFile.path required")
    with open(path, "r") as f:
        docs = list(yaml.safe_load_all(f.read()))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, apply_manifest_docs, ctx.apis, docs, ctx.namespace)
