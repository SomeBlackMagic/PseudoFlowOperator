import time
import uuid
import os
import logging
from typing import Dict, List, Optional

from kubernetes import client
from kubernetes.client import ApiException

logger = logging.getLogger("pseudoflow.kube")

# Получаем образ из ENV (для поддержки air-gapped сред) или используем дефолтный
RUNNER_IMAGE = os.getenv("PSEUDOFLOW_RUNNER_IMAGE", "alpine:3.20")


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
        metadata=client.V1ObjectMeta(
            name=name,
            labels={
                "created-by": "pseudoflow-operator",
                "pseudoflow.io/component": "exec-runner"
            }
        ),
        spec=client.V1PodSpec(
            restart_policy="Never",
            node_selector=node_selector,
            host_network=True if privileged else False,
            containers=[
                client.V1Container(
                    name="runner",
                    image=RUNNER_IMAGE,  # Используем переменную модуля
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

    try:
        core.create_namespaced_pod(namespace=namespace, body=pod)
    except ApiException as e:
        logger.error(f"Failed to create execution pod: {e}")
        raise

    end = time.time() + timeout

    logs = ""  # FIX: Инициализация переменной logs

    try:
        while time.time() < end:
            try:
                p = core.read_namespaced_pod(name=name, namespace=namespace)
            except ApiException as e:
                if e.status == 404:
                    # Под удален до завершения
                    raise RuntimeError("Execution pod was unexpectedly deleted.")
                raise

            phase = (p.status.phase or "").lower()
            if phase in ("succeeded", "failed"):
                break
            time.sleep(2)

        # Пытаемся прочитать логи
        logs = core.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            _return_http_data_only=True,
            _preload_content=True,
        )
    except Exception as e:  # FIX: Избегаем голого Exception, но нужно для общих ошибок
        logger.warning(f"Error during execution or reading logs: {e}")
        # Если под завершился неудачей, возвращаем статус
        if phase == "failed":
            raise RuntimeError(f"Command execution failed. Logs: {logs}")
        raise  # Перебрасываем другие ошибки
    finally:
        # Гарантированное удаление пода
        try:
            core.delete_namespaced_pod(
                name=name, namespace=namespace, grace_period_seconds=0
            )
        except Exception:
            logger.debug(f"Failed to delete pod {name}/{namespace}, might be already gone.")

    return logs