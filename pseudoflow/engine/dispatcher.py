from typing import Dict, Callable, Awaitable

from .context import FlowContext
from pseudoflow.steps import (
    log as step_log,
    sleep as step_sleep,
    apply as step_apply,
    delete as step_delete,
    exec as step_exec,
    exec_node as step_exec_node,
    config_file as step_config_file,
    patch_file as step_patch_file,
    apply_file as step_apply_file,
    delete_file as step_delete_file,
    include as step_include,
    wait_for as step_wait_for,
    set_label as step_set_label,
    remove_label as step_remove_label,
    patch_label as step_patch_label,
    template as step_template,
    script as step_script,
    eval as step_eval,  # <-- Импортируем новый модуль
)

Handler = Callable[[dict, FlowContext], Awaitable[None]]

_HANDLERS: Dict[str, Handler] = {
    "log": step_log.handle,
    "sleep": step_sleep.handle,
    "apply": step_apply.handle,
    "delete": step_delete.handle,
    "exec": step_exec.handle,
    "execNode": step_exec_node.handle,
    "configFile": step_config_file.handle,
    "patchFile": step_patch_file.handle,
    "applyFile": step_apply_file.handle,
    "deleteFile": step_delete_file.handle,
    "include": step_include.handle,
    "waitFor": step_wait_for.handle,
    "setLabel": step_set_label.handle,
    "removeLabel": step_remove_label.handle,
    "patchLabel": step_patch_label.handle,
    "template": step_template.handle,
    "script": step_script.handle,
    "eval": step_eval.handle,  # <-- Регистрируем handler
}


async def execute_step(step_type: str, step: dict, ctx: FlowContext) -> None:
    handler = _HANDLERS.get(step_type)
    if not handler:
        raise ValueError(f"unsupported step.type '{step_type}'")
    await handler(step, ctx)