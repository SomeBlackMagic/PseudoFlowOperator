import asyncio
import json

from pseudoflow.engine.context import FlowContext
from pseudoflow.kube import patch_labels


async def handle(step: dict, ctx: FlowContext) -> None:
    target = step.get("target") or {}
    kind = target.get("kind")
    ns = target.get("namespace", ctx.namespace)
    from_var = step.get("fromVar")

    if not kind:
        raise ValueError("patchLabel: target.kind required")

    if not from_var or from_var not in ctx.vars:
        raise ValueError("patchLabel.fromVar missing or undefined")

    raw = ctx.vars[from_var]
    mapping = json.loads(raw) if isinstance(raw, str) else raw

    loop = asyncio.get_event_loop()
    for name, add_labels in mapping.items():
        await loop.run_in_executor(None, patch_labels, ctx.apis, kind, ns, name, add_labels, [])
