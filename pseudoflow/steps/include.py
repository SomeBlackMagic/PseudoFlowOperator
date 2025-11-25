import asyncio
import requests
import yaml

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import apply_manifest_docs


async def handle(step: dict, ctx: FlowContext) -> None:
    src = step.get("source")
    if not src:
        raise ValueError("include.source required")

    if src.startswith("http://") or src.startswith("https://"):
        resp = requests.get(src, timeout=20)
        resp.raise_for_status()
        manifests = resp.text
    else:
        with open(src, "r") as f:
            manifests = f.read()

    docs = list(yaml.safe_load_all(manifests))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, apply_manifest_docs, ctx.apis, docs, ctx.namespace)
