from typing import Any, Dict, List

from kubernetes import client, utils


def apply_manifest_docs(apis, docs, default_namespace=None):
    k8s_client = apis["dyn"]
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
        core.delete_namespaced_config_map(name, ns)
        return
    if gv == "v1" and kind == "Secret":
        core.delete_namespaced_secret(name, ns)
        return
    if gv == "v1" and kind == "Service":
        core.delete_namespaced_service(name, ns)
        return
    if gv == "apps/v1" and kind == "Deployment":
        apps.delete_namespaced_deployment(name, ns)
        return
    if gv == "apps/v1" and kind == "DaemonSet":
        apps.delete_namespaced_daemon_set(name, ns)
        return
    if gv == "apps/v1" and kind == "StatefulSet":
        apps.delete_namespaced_stateful_set(name, ns)
        return
    raise ValueError(f"delete unsupported for {gv}/{kind}")


def patch_labels(apis, kind: str, ns: str | None, name: str, add: Dict[str, str], remove_keys: List[str]):
    core = apis["core"]
    apps = apis["apps"]
    body = {"metadata": {"labels": add or {}}}
    for k in remove_keys or []:
        body["metadata"]["labels"][k] = None

    if kind == "Node":
        client.CoreV1Api().patch_node(name, body)
        return
    if kind == "Pod":
        core.patch_namespaced_pod(name=name, namespace=ns, body=body)
        return
    if kind == "Deployment":
        apps.patch_namespaced_deployment(name=name, namespace=ns, body=body)
        return
    if kind == "DaemonSet":
        apps.patch_namespaced_daemon_set(name=name, namespace=ns, body=body)
        return
    if kind == "StatefulSet":
        apps.patch_namespaced_stateful_set(name=name, namespace=ns, body=body)
        return
    if kind == "Service":
        core.patch_namespaced_service(name=name, namespace=ns, body=body)
        return
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
    if kind == "StatefulSet":
        items = apps.list_namespaced_stateful_set(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    if kind == "Service":
        items = core.list_namespaced_service(namespace=ns, label_selector=selector).items
        return [i.metadata.name for i in items]
    raise ValueError(f"selector listing unsupported kind '{kind}'")


def select_nodes(apis, selector) -> List[str]:
    core = apis["core"]
    if isinstance(selector, str):
        label = selector
    else:
        label = ",".join(f"{k}={v}" for k, v in (selector or {}).items())
    items = core.list_node(label_selector=label).items
    return [i.metadata.name for i in items]
