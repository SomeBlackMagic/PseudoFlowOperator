
import asyncio
import os
import kopf
import logging
from pseudoflow.engine import FlowEngine
from pseudoflow.kube import ensure_crd_installed, get_k8s_api_clients

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

@kopf.on.startup()
async def _startup(settings: kopf.OperatorSettings, **_):
    settings.persistence.finalizer = 'ops.example.com/pseudoflow-finalizer'
    settings.networking.request_timeout = 30
    settings.networking.connect_timeout = 5
    await asyncio.get_event_loop().run_in_executor(None, ensure_crd_installed)
    logger.info("CRD check complete")

@kopf.on.create('ops.example.com', 'v1alpha1', 'pseudoflows')
@kopf.on.update('ops.example.com', 'v1alpha1', 'pseudoflows')
async def reconcile(spec, status, meta, body, patch, **_):
    ns = meta.get('namespace')
    name = meta.get('name')
    gen = meta.get('generation')

    patch.status.setdefault('observedGeneration', 0)
    patch.status.setdefault('phase', 'Pending')
    patch.status['observedGeneration'] = gen
    patch.status['phase'] = 'Running'
    patch.status['message'] = 'started'

    apis = get_k8s_api_clients()
    engine = FlowEngine(apis)

    try:
        result = await engine.run_flow(name=name, namespace=ns, spec=spec)
        patch.status['phase'] = 'Succeeded'
        patch.status['message'] = f"ok: {result.summary}"
        patch.status['conditions'] = [{
            "type": "Ready", "status": "True",
            "reason": "RunSucceeded", "message": result.summary
        }]
    except Exception as e:
        logger.exception("Flow failed")
        patch.status['phase'] = 'Failed'
        patch.status['message'] = str(e)
        patch.status['conditions'] = [{
            "type": "Degraded", "status": "True",
            "reason": "RunFailed", "message": str(e)
        }]

def main():
    kopf.configure(verbose=True)
    kopf.run()
