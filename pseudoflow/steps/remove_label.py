import asyncio

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import list_resources_by_selector, patch_labels


async def handle(step: dict, ctx: FlowContext) -> None:
    target = step.get("target") or {}
    keys = step.get("keys", []) or []
    kind = target.get("kind")
    ns = target.get("namespace", ctx.namespace)

    if not kind:
        raise ValueError("removeLabel: target.kind required")

    selector = target.get("selector")
    if selector:
        names = list_resources_by_selector(ctx.apis, kind, ns, selector)
    else:
        name = target.get("name")
        if not name:
            raise ValueError("removeLabel requires target.name or target.selector")
        names = [name]

    loop = asyncio.get_event_loop()
    for name in names:
        await loop.run_in_executor(None, patch_labels, ctx.apis, kind, ns, name, {}, keys)
