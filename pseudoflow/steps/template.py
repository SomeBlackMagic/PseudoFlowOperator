from pseudoflow.engine.context import FlowContext
from pseudoflow.util.templating import render_str


async def handle(step: dict, ctx: FlowContext) -> None:
    tpl = step.get("template", "")
    out_path = step.get("output")
    rendered = render_str(tpl, ctx.vars)

    if out_path:
        with open(out_path, "w") as f:
            f.write(rendered)
    else:
        var = step.get("var")
        if var:
            ctx.vars[var] = rendered
