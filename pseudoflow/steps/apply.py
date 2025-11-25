import asyncio
import yaml

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import apply_manifest_docs


async def handle(step: dict, ctx: FlowContext) -> None:
    manifests_str = step.get("manifests", "")
    docs = list(yaml.safe_load_all(manifests_str)) if manifests_str else []
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, apply_manifest_docs, ctx.apis, docs, ctx.namespace)
