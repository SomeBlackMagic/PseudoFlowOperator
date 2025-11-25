import yaml
from kubernetes import client, utils
from kubernetes.client import ApiException

from .client import get_k8s_api_clients

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
                          - if
                          - when
                          - exec
                          - execNode
                          - configFile
                          - patchFile
                          - applyFile
                          - deleteFile
                          - include
                          - waitFor
                          - setLabel
                          - removeLabel
                          - patchLabel
                          - loop
                          - loopNodes
                          - template
                          - script
                          - retry
                          - onError
                          - parallel
                          - includeFlow
                options:
                  type: object
                  properties:
                    timeoutSeconds:
                      type: integer
            status:
              type: object
"""


def ensure_crd_installed() -> None:
    apis = get_k8s_api_clients()
    api_ext = client.ApiextensionsV1Api()
    try:
        api_ext.read_custom_resource_definition("pseudoflows.ops.example.com")
        return
    except ApiException as e:
        if e.status != 404:
            raise
    utils.create_from_yaml(apis["dyn"], yaml_objects=list(yaml.safe_load_all(_CRD)))
