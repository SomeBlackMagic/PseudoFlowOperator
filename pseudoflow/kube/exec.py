import time
import uuid
from typing import Dict, List, Optional

from kubernetes import client


def run_pod_and_get_logs(
    apis,
    namespace: str,
    command: str,
    node_selector: Optional[Dict[str, str]] = None,
    privileged: bool = False,
    host_paths: Optional[List[Dict[str, str]]] = None,
    timeout: int = 600,
):
    core = apis["core"]
    name = f"pseudoflow-exec-{str(uuid.uuid4())[:8]}"
    volumes = []
    volume_mounts = []

    if host_paths:
        for i, hp in enumerate(host_paths):
            vname = f"hp{i}"
            volumes.append(
                client.V1Volume(
                    name=vname,
                    host_path=client.V1HostPathVolumeSource(
                        path=hp["hostPath"],
                        type=hp.get("type"),
                    ),
                )
            )
            volume_mounts.append(
                client.V1VolumeMount(
                    name=vname,
                    mount_path=hp["mountPath"],
                    read_only=hp.get("readOnly", False),
                )
            )

    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1PodSpec(
            restart_policy="Never",
            node_selector=node_selector,
            host_network=True if privileged else False,
            containers=[
                client.V1Container(
                    name="runner",
                    image="alpine:3.20",
                    command=["/bin/sh", "-lc", command],
                    security_context=client.V1SecurityContext(
                        privileged=privileged
                    )
                    if privileged
                    else None,
                    volume_mounts=volume_mounts or None,
                )
            ],
            volumes=volumes or None,
            tolerations=[client.V1Toleration(operator="Exists")]
            if node_selector
            else None,
        ),
    )

    core.create_namespaced_pod(namespace=namespace, body=pod)
    end = time.time() + timeout
    while time.time() < end:
        p = core.read_namespaced_pod(name=name, namespace=namespace)
        phase = (p.status.phase or "").lower()
        if phase in ("succeeded", "failed"):
            break
        time.sleep(2)
    logs = core.read_namespaced_pod_log(
        name=name,
        namespace=namespace,
        _return_http_data_only=True,
        _preload_content=True,
    )
    try:
        core.delete_namespaced_pod(
            name=name, namespace=namespace, grace_period_seconds=0
        )
    except Exception:
        pass
    return logs
