from typing import Dict, Any

from kubernetes import client, config

_cached_clients: Dict[str, Any] | None = None


def get_k8s_api_clients() -> Dict[str, Any]:
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
        "dyn": client.ApiClient(),
    }
    return _cached_clients
