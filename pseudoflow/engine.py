
import asyncio
import copy
import time
import yaml
from typing import Any, Dict, List
from .kube import (
    apply_manifest_docs, delete_target, wait_for_resource_condition,
    patch_labels, list_resources_by_selector
)
from .templating import render_str

class RunResult:
    def __init__(self):
        self.steps_ok = 0
        self.steps_fail = 0
        self.start = time.time()

    @property
    def summary(self) -> str:
        dur = time.time() - self.start
        return f"steps_ok={self.steps_ok} steps_fail={self.steps_fail} duration_sec={round(dur,2)}"

class FlowEngine:
    def __init__(self, apis):
        self.apis = apis

    async def run_flow(self, name: str, namespace: str | None, spec: Dict[str, Any]) -> RunResult:
        vars_map = spec.get('vars', {}) or {}
        steps = spec.get('steps', []) or []
        options = spec.get('options', {}) or {}
        timeout = options.get('timeoutSeconds', 0)
        if timeout:
            return await asyncio.wait_for(self._run_steps(steps, vars_map, namespace), timeout=timeout)
        return await self._run_steps(steps, vars_map, namespace)

    async def _run_steps(self, steps: List[Dict[str, Any]], vars_map: Dict[str, str], namespace: str | None) -> RunResult:
        result = RunResult()
        for step in steps:
            try:
                await self._run_step(step, vars_map, namespace)
                result.steps_ok += 1
            except Exception:
                result.steps_fail += 1
                raise
        return result

    async def _run_step(self, step: Dict[str, Any], vars_map: Dict[str, str], namespace: str | None):
        stype = step.get('type')
        if not stype:
            raise ValueError("step.type is required")

        step = _deep_render(copy.deepcopy(step), vars_map)

        if stype == 'log':
            msg = step.get('message', '')
            print(f"[log] {msg}")
            return

        if stype == 'sleep':
            secs = int(step.get('seconds', 1))
            await asyncio.sleep(secs)
            return

        if stype == 'apply':
            manifests = step.get('manifests')
            if not manifests:
                raise ValueError("apply.manifests is required")
            docs = list(yaml.safe_load_all(manifests))
            await asyncio.get_event_loop().run_in_executor(None, apply_manifest_docs, self.apis, docs, namespace)
            return

        if stype == 'delete':
            target = step.get('target')
            if not target:
                raise ValueError("delete.target is required")
            await asyncio.get_event_loop().run_in_executor(None, delete_target, self.apis, target, namespace)
            return

        if stype == 'waitFor':
            res = step.get('resource', {})
            cond = step.get('condition', 'Exist')
            tout = int(step.get('timeoutSeconds', 300))
            interval = int(step.get('intervalSeconds', 5))
            await wait_for_resource_condition(self.apis, res, cond, tout, interval, namespace)
            return

        if stype in ('setLabel', 'removeLabel'):
            target = step.get('target') or {}
            labels = step.get('labels', {}) if stype == 'setLabel' else {}
            remove_keys = step.get('keys', []) if stype == 'removeLabel' else []
            selector = target.get('selector')
            kind = target.get('kind')
            ns = target.get('namespace', namespace)

            if not kind:
                raise ValueError("label step requires target.kind")

            if selector:
                names = list_resources_by_selector(self.apis, kind, ns, selector)
            else:
                nm = target.get('name')
                if not nm:
                    raise ValueError("label step requires target.name or target.selector")
                names = [nm]

            for name in names:
                await asyncio.get_event_loop().run_in_executor(
                    None, patch_labels, self.apis, kind, ns, name, labels, remove_keys
                )
            return

        if stype == 'loop':
            iterable_expr = step.get('forEach')
            if iterable_expr is None:
                raise ValueError("loop.forEach is required")
            items = iterable_expr
            if isinstance(items, str):
                if items.strip().startswith('['):
                    items = yaml.safe_load(items)
                else:
                    items = [s for s in items.split() if s]
            if not isinstance(items, list):
                raise ValueError("loop.forEach must resolve to list")
            substeps = step.get('steps', [])
            for it in items:
                local_vars = dict(vars_map)
                local_vars.update({"item": str(it)})
                await self._run_steps(_render_steps(substeps, local_vars), local_vars, namespace)
            return

        if stype == 'parallel':
            groups = step.get('steps', [])
            if not isinstance(groups, list) or not all(isinstance(g, list) for g in groups):
                raise ValueError("parallel.steps must be list of step-lists")
            await asyncio.gather(*[
                self._run_steps(_render_steps(g, vars_map), vars_map, namespace) for g in groups
            ])
            return

        raise ValueError(f"unsupported step.type '{stype}' in MVP")

def _render_steps(steps, vars_map):
    return [_deep_render(copy.deepcopy(s), vars_map) for s in steps]

def _deep_render(obj, vars_map):
    if isinstance(obj, str):
        return render_str(obj, vars_map)
    if isinstance(obj, list):
        return [_deep_render(x, vars_map) for x in obj]
    if isinstance(obj, dict):
        return {k: _deep_render(v, vars_map) for k, v in obj.items()}
    return obj
