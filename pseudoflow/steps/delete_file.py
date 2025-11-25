import asyncio
import yaml
from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import delete_target


async def handle(step: dict, ctx: FlowContext) -> None:
    path = step.get("path")
    if not path:
        raise ValueError("deleteFile.path required")

    with open(path, "r") as f:
        docs = list(yaml.safe_load_all(f.read()))

    loop = asyncio.get_event_loop()
    for doc in docs:
        if not doc:
            continue
        target = {
            "apiVersion": doc.get("apiVersion", "v1"),
            "kind": doc.get("kind"),
            "name": doc.get("metadata", {}).get("name"),
            "namespace": doc.get("metadata", {}).get("namespace", ctx.namespace),
        }
        await loop.run_in_executor(None, delete_target, ctx.apis, target, ctx.namespace)
