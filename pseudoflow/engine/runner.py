import asyncio
import copy
import logging
import time
from typing import Any, Dict, List, Optional

from jsonpath_ng import parse as jp_parse
from kubernetes import client

from .context import FlowContext
from .dispatcher import execute_step
from pseudoflow.kube import select_nodes
from pseudoflow.util.templating import render_str

logger = logging.getLogger("pseudoflow.engine")


class RunResult:
    def __init__(self):
        self.steps_ok = 0
        self.steps_fail = 0
        self.start = time.time()

    @property
    def summary(self) -> str:
        dur = time.time() - self.start
        return f"steps_ok={self.steps_ok} steps_fail={self.steps_fail} duration_sec={round(dur, 2)}"


class FlowEngine:
    def __init__(self, apis, operator_namespace: str):
        self.apis = apis
        self.operator_ns = operator_namespace

    async def run_flow(self, name: str, namespace: Optional[str], spec: Dict[str, Any]) -> RunResult:
        vars_map: Dict[str, str] = spec.get("vars", {}) or {}
        steps = spec.get("steps", []) or []
        options = spec.get("options", {}) or {}
        timeout = options.get("timeoutSeconds", 0)

        ctx = FlowContext(
            apis=self.apis,
            operator_ns=self.operator_ns,
            namespace=namespace,
            vars=vars_map,
        )

        if timeout:
            return await asyncio.wait_for(self._run_steps(steps, ctx), timeout=timeout)
        return await self._run_steps(steps, ctx)

    async def _run_steps(self, steps: List[Dict[str, Any]], ctx: FlowContext) -> RunResult:
        result = RunResult()
        prev_failed = False
        last_error: Optional[Exception] = None

        for step in steps:
            try:
                await self._run_step(step, ctx, prev_failed, last_error)
                prev_failed = False
                last_error = None
                result.steps_ok += 1
            except Exception as e:
                prev_failed = True
                last_error = e
                result.steps_fail += 1
                logger.error("Step failed: %s", e)
                raise
        return result

    async def _run_step(
            self,
            step: Dict[str, Any],
            ctx: FlowContext,
            prev_failed: bool,
            last_error: Optional[Exception],
    ):
        stype = step.get("type")
        if not stype:
            raise ValueError("step.type is required")

        step = _deep_render(copy.deepcopy(step), ctx.vars)

        # retry
        if stype == "retry":
            attempts = int(step.get("attempts", 3))
            backoff = int(step.get("backoffSeconds", 2))
            substeps = step.get("steps", [])
            err: Optional[Exception] = None
            for i in range(attempts):
                try:
                    await self._run_steps(substeps, ctx)
                    return
                except Exception as e:
                    err = e
                    logger.warning("retry attempt %s failed: %s", i + 1, e)
                    await asyncio.sleep(backoff * (i + 1))
            raise err if err else RuntimeError("retry failed")

        # onError
        if stype == "onError":
            if not prev_failed or last_error is None:
                logger.debug("onError skipped: no previous error")
                return
            substeps = step.get("steps", [])
            ctx.vars["__last_error__"] = str(last_error)
            await self._run_steps(substeps, ctx)
            return

        # if
        if stype == "if":
            cond = step.get("condition", {})
            if _eval_condition(ctx.apis, cond, ctx.namespace):
                await self._run_steps(step.get("then", []), ctx)
            else:
                await self._run_steps(step.get("else", []), ctx)
            return

        # when
        if stype == "when":
            cond = step.get("condition", {})
            if _eval_condition(ctx.apis, cond, ctx.namespace):
                await self._run_steps(step.get("steps", []), ctx)
            return

        # loop
        if stype == "loop":
            items = _parse_iterable(step.get("forEach"))
            substeps = step.get("steps", [])
            for it in items:
                local_vars = dict(ctx.vars)
                local_vars["item"] = str(it)
                local_ctx = FlowContext(
                    apis=ctx.apis,
                    operator_ns=ctx.operator_ns,
                    namespace=ctx.namespace,
                    vars=local_vars,
                )
                await self._run_steps(_render_steps(substeps, local_ctx.vars), local_ctx)
            return

        # loopNodes
        if stype == "loopNodes":
            nodes = select_nodes(ctx.apis, step.get("selector", {}))
            substeps = step.get("steps", [])
            for node in nodes:
                local_vars = dict(ctx.vars)
                local_vars["node"] = node
                local_ctx = FlowContext(
                    apis=ctx.apis,
                    operator_ns=ctx.operator_ns,
                    namespace=ctx.namespace,
                    vars=local_vars,
                )
                await self._run_steps(_render_steps(substeps, local_ctx.vars), local_ctx)
            return

        # parallel
        if stype == "parallel":
            groups = step.get("steps", [])
            wait_all = bool(step.get("waitForAll", True))
            coros = [
                self._run_steps(
                    _render_steps(group, ctx.vars),
                    FlowContext(
                        apis=ctx.apis,
                        operator_ns=ctx.operator_ns,
                        namespace=ctx.namespace,
                        vars=dict(ctx.vars),
                    ),
                )
                for group in groups
            ]
            if wait_all:
                await asyncio.gather(*coros)
            else:
                # FIX: Используем asyncio.wait с return_when=asyncio.FIRST_EXCEPTION
                await asyncio.wait(coros, return_when=asyncio.FIRST_EXCEPTION)
            return

        # includeFlow
        if stype == "includeFlow":
            name = step.get("name")
            ns = step.get("namespace", ctx.namespace)
            inherit = bool(step.get("inheritVars", False))
            if not name:
                raise ValueError("includeFlow.name required")
            obj = ctx.apis["custom"].get_namespaced_custom_object(
                group="ops.example.com",
                version="v1alpha1",
                namespace=ns,
                plural="pseudoflows",
                name=name,
            )
            sub_vars = dict(ctx.vars) if inherit else {}
            sub_ctx = FlowContext(
                apis=ctx.apis,
                operator_ns=ctx.operator_ns,
                namespace=ns,
                vars=sub_vars,
            )
            await self._run_steps(obj.get("spec", {}).get("steps", []), sub_ctx)
            return

        # default: delegate to step handler
        await execute_step(stype, step, ctx)


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


def _parse_iterable(expr):
    if isinstance(expr, list):
        return expr
    if isinstance(expr, str):
        s = expr.strip()
        if s.startswith("["):
            import yaml
            return yaml.safe_load(s)
        return [p for p in s.split() if p]
    raise ValueError("loop.forEach must be list or string")


def _eval_condition(apis, condition: Dict[str, Any], default_ns: Optional[str]) -> bool:
    res = condition.get("resource")
    if not res:
        return False
    json_path = condition.get("jsonPath")  # FIX: PEP8 jsonPath -> json_path
    op = condition.get("op", "equals")
    value = condition.get("value", "")

    # Парсинг GVK
    gv = res.get("apiVersion", "v1")
    kind = res.get("kind")
    name = res.get("name")
    ns = res.get("namespace", default_ns)

    if not kind or not name:
        return False

    core = apis["core"]
    apps = apis["apps"]
    custom = apis["custom"]

    obj = None
    try:
        # Пытаемся определить метод загрузки на основе GVK
        if "/" in gv:
            group, version = gv.split("/", 1)
        else:
            group, version = "", gv

        # 1. Core Resources (v1)
        if group == "" and version == "v1":
            if kind == "ConfigMap":
                obj = core.read_namespaced_config_map(name, ns)
            elif kind == "Service":
                obj = core.read_namespaced_service(name, ns)
            elif kind == "Pod":
                obj = core.read_namespaced_pod(name, ns)
            elif kind == "Secret":
                obj = core.read_namespaced_secret(name, ns)
            elif kind == "Node":
                obj = core.read_node(name)
            else:
                pass

        # 2. Apps Resources (apps/v1)
        elif group == "apps" and version == "v1":
            if kind == "Deployment":
                obj = apps.read_namespaced_deployment(name, ns)
            elif kind == "DaemonSet":
                obj = apps.read_namespaced_daemon_set(name, ns)
            elif kind == "StatefulSet":
                obj = apps.read_namespaced_stateful_set(name, ns)
            else:
                pass

        # 3. Custom Resources (CRDs) и остальные
        if obj is None:
            # Превращаем kind в plural (простая эвристика)
            plural = kind.lower() + "s"
            try:
                obj_dict = custom.get_namespaced_custom_object(
                    group=group,
                    version=version,
                    namespace=ns,
                    plural=plural,
                    name=name
                )
                data = obj_dict
            except client.exceptions.ApiException:
                return False

    except Exception:
        return False

    # Унификация данных (модель -> dict)
    if obj and not isinstance(obj, dict):
        try:
            data = obj.to_dict()
        except AttributeError:
            data = obj
    elif obj:
        data = obj
    elif 'data' not in locals():
        return False

    matches = [m.value for m in jp_parse(json_path).find(data)] if json_path else [data]

    def cmp(m):
        m_str = str(m)
        val_str = str(value)
        if op == "equals":
            return m_str == val_str
        if op == "notEquals":
            return m_str != val_str
        if op == "contains":
            return val_str in m_str

        try:
            m_float = float(m)
            val_float = float(value)
            if op == "greaterThan":
                return m_float > val_float
            if op == "lessThan":
                return m_float < val_float
        except (ValueError, TypeError):
            pass
        return False

    return any(cmp(m) for m in matches)