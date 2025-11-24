
import time
from typing import Any, Dict, List
import yaml
from kubernetes import client, config, utils
from kubernetes.client import ApiException

_cached_clients = None

def get_k8s_api_clients():
    global _cached_clients
    if _cached_clients:
        return _cached_clients
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    _cached_clients = {
        "core": client.CoreV1Api(),
        "apps": client.AppsV1Api(),
        "rbac": client.RbacAuthorizationV1Api(),
        "custom": client.CustomObjectsApi(),
        "dynamic": client.ApiClient(),
    }
    return _cached_clients

_CRD = """
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: pseudoflows.ops.example.com
spec:
  group: ops.example.com
  scope: Namespaced
  names:
    kind: PseudoFlow
    plural: pseudoflows
    singular: pseudoflow
    shortNames: ["pflow"]
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                vars:
                  type: object
                  additionalProperties:
                    type: string
                steps:
                  type: array
                  items:
                    type: object
                    required: ["type"]
                    properties:
                      type:
                        type: string
                        enum:
                          - log
                          - sleep
                          - apply
                          - delete
                          - waitFor
                          - setLabel
                          - removeLabel
                          - loop
                          - parallel
                options:
                  type: object
                  properties:
                    timeoutSeconds:
                      type: integer
            status:
              type: object
              properties:
                observedGeneration:
                  type: integer
                phase:
                  type: string
                message:
                  type: string
                conditions:
                  type: array
                  items:
                    type: object
"""

def ensure_crd_installed():
    apis = get_k8s_api_clients()
    api_ext = client.ApiextensionsV1Api()
    try:
        api_ext.read_custom_resource_definition("pseudoflows.ops.example.com")
        return
    except ApiException as e:
        if e.status != 404:
            raise
    utils.create_from_yaml(apis["dynamic"], yaml_objects=list(yaml.safe_load_all(_CRD)))

def apply_manifest_docs(apis, docs, default_namespace=None):
    k8s_client = apis["dynamic"]
    for doc in docs:
        if not doc or not isinstance(doc, dict):
            continue
        utils.create_from_dict(k8s_client, data=doc, verbose=False)

def delete_target(apis, target: Dict[str, Any], default_namespace=None):
    gv = target.get("apiVersion", "v1")
    kind = target["kind"]
    name = target["name"]
    ns = target.get("namespace", default_namespace)

    core = apis["core"]
    apps = apis["apps"]

    if gv == "v1" and kind == "ConfigMap":
        core.delete_namespaced_config_map(name, ns); return
    if gv == "v1" and kind == "Service":
        core.delete_namespaced_service(name, ns); return
    if gv == "apps/v1" and kind == "Deployment":
        apps.delete_namespaced_deployment(name, ns); return
    if gv == "apps/v1" and kind == "DaemonSet":
        apps.delete_namespaced_daemon_set(name, ns); return
    raise ValueError(f"delete unsupported for {gv}/{kind}")

def wait_for_resource_condition(apis, res: Dict[str, Any], condition: str, timeout: int, interval: int, default_namespace=None):
    end = time.time() + timeout
    gv = res.get("apiVersion", "v1")
    kind = res["kind"]
    name = res["name"]
    ns = res.get("namespace", default_namespace)

    core = apis["core"]
    apps = apis["apps"]

    def exists():
        try:
            if gv == "v1" and kind == "Service":
                core.read_namespaced_service(name, ns); return True
            if gv == "v1" and kind == "ConfigMap":
                core.read_namespaced_config_map(name, ns); return True
            if gv == "apps/v1" and kind == "Deployment":
                apps.read_namespaced_deployment(name, ns); return True
            if gv == "apps/v1" and kind == "DaemonSet":
                apps.read_namespaced_daemon_set(name, ns); return True
            return False
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def ready():
        if gv == "apps/v1" and kind == "Deployment":
            obj = apps.read_namespaced_deployment(name, ns)
            desired = obj.status.replicas or 0
            avail = obj.status.available_replicas or 0
            return desired == avail and desired > 0
        if gv == "apps/v1" and kind == "DaemonSet":
            obj = apps.read_namespaced_daemon_set(name, ns)
            desired = obj.status.desired_number_scheduled or 0
            rd = obj.status.number_ready or 0
            return desired == rd and desired > 0
        return False

    cond = condition.lower()
    if cond == "exist":
        while time.time() < end:
            if exists(): return
            time.sleep(interval)
        raise TimeoutError("waitFor Exist timed out")

    if cond == "deleted":
        while time.time() < end:
            if not exists(): return
            time.sleep(interval)
        raise TimeoutError("waitFor Deleted timed out")

    if cond == "ready":
        while time.time() < end:
            if ready(): return
            time.sleep(interval)
        raise TimeoutError("waitFor Ready timed out")

    raise ValueError(f"Unsupported waitFor condition '{condition}' in MVP")

def patch_labels(apis, kind: str, ns: str | None, name: str, add: Dict[str, str], remove_keys: List[str]):
    core = apis["core"]
    apps = apis["apps"]
    body = {"metadata": {"labels": add or {}}}
    for k in remove_keys or []:
        body["metadata"]["labels"][k] = None

    if kind == "Node":
        client.CoreV1Api().patch_node(name, body); return
    if kind == "Pod":
        core.patch_namespaced_pod(name=name, namespace=ns, body=body); return
    if kind == "Deployment":
        apps.patch_namespaced_deployment(name=name, namespace=ns, body=body); return
    if kind == "DaemonSet":
        apps.patch_namespaced_daemon_set(name=name, namespace=ns, body=body); return
    if kind == "Service":
        core.patch_namespaced_service(name=name, namespace=ns, body=body); return
    raise ValueError(f"patchLabels unsupported kind '{kind}'")

def list_resources_by_selector(apis, kind: str, ns: str | None, selector: str) -> List[str]:
    core = apis["core"]
    apps = apis["apps"]
    if kind == "Node":
        items = core.list_node(label_selector=selector).items
        return [i.metadata.name for i in items]
    if kind == "Pod":
        items = core.list_namespaced_pod(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    if kind == "Deployment":
        items = apps.list_namespaced_deployment(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    if kind == "DaemonSet":
        items = apps.list_namespaced_daemon_set(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    if kind == "Service":
        items = core.list_namespaced_service(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    raise ValueError(f"selector listing unsupported kind '{kind}'")
