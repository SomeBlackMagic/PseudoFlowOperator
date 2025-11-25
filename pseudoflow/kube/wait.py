import time
from typing import Any, Dict, Optional

from jsonpath_ng import parse as jp_parse
from kubernetes.client import ApiException


def wait_for_resource_condition(
    apis,
    res: Dict[str, Any],
    condition: str,
    timeout: int,
    interval: int,
    default_namespace: Optional[str] = None,
    jsonpath: Optional[str] = None,
    op: Optional[str] = None,
    value: Optional[str] = None,
):
    end = time.time() + timeout
    gv = res.get("apiVersion", "v1")
    kind = res["kind"]
    name = res["name"]
    ns = res.get("namespace", default_namespace)

    core = apis["core"]
    apps = apis["apps"]

    def get_obj():
        if gv == "v1" and kind == "Service":
            return core.read_namespaced_service(name, ns)
        if gv == "v1" and kind == "ConfigMap":
            return core.read_namespaced_config_map(name, ns)
        if gv == "apps/v1" and kind == "Deployment":
            return apps.read_namespaced_deployment(name, ns)
        if gv == "apps/v1" and kind == "DaemonSet":
            return apps.read_namespaced_daemon_set(name, ns)
        if gv == "apps/v1" and kind == "StatefulSet":
            return apps.read_namespaced_stateful_set(name, ns)
        return None

    def exists():
        try:
            return get_obj() is not None
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def ready():
        if gv == "apps/v1" and kind == "Deployment":
            obj = get_obj()
            desired = obj.status.replicas or 0
            avail = obj.status.available_replicas or 0
            return desired == avail and desired > 0
        if gv == "apps/v1" and kind == "DaemonSet":
            obj = get_obj()
            desired = obj.status.desired_number_scheduled or 0
            rd = obj.status.number_ready or 0
            return desired == rd and desired > 0
        if gv == "apps/v1" and kind == "StatefulSet":
            obj = get_obj()
            replicas = obj.status.replicas or 0
            ready_replicas = obj.status.ready_replicas or 0
            return replicas == ready_replicas and replicas > 0
        return False

    cond = condition.lower()
    if cond == "exist":
        while time.time() < end:
            if exists():
                return
            time.sleep(interval)
        raise TimeoutError("waitFor Exist timed out")

    if cond == "deleted":
        while time.time() < end:
            if not exists():
                return
            time.sleep(interval)
        raise TimeoutError("waitFor Deleted timed out")

    if cond in ("ready", "available", "healthy"):
        while time.time() < end:
            if ready():
                return
            time.sleep(interval)
        raise TimeoutError(f"waitFor {condition} timed out")

    if cond == "custom":
        if not jsonpath or not op:
            raise ValueError("Custom condition requires jsonPath and op")
        expr = jp_parse(jsonpath)
        while time.time() < end:
            obj = get_obj()
            if obj is None:
                time.sleep(interval)
                continue
            data = obj.to_dict()
            matches = [m.value for m in expr.find(data)]
            ok = False
            if op == "equals":
                ok = any(str(m) == str(value) for m in matches)
            elif op == "notEquals":
                ok = any(str(m) != str(value) for m in matches)
            elif op == "contains":
                ok = any(str(value) in str(m) for m in matches)
            elif op == "greaterThan":
                ok = any(float(m) > float(value)) if matches else False
            elif op == "lessThan":
                ok = any(float(m) < float(value)) if matches else False
            else:
                raise ValueError(f"Unsupported op {op}")
            if ok:
                return
            time.sleep(interval)
        raise TimeoutError("waitFor Custom timed out")

    raise ValueError(f"Unsupported waitFor condition '{condition}'")
