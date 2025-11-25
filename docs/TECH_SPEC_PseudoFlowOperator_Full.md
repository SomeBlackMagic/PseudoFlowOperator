# Техническое задание: Kubernetes оператор 

**PseudoFlow Operator** — расширенная спецификация

---

## 1. Цель
Универсальный оператор, исполняющий декларативные **flows** в CR `PseudoFlow`. Поддерживает ветвления, ожидание состояний, манипуляцию объектами API, операции на узлах, работу с файлами и метаданными ресурсов на основе вывода команд.

---

## 2. Архитектура

```
User
  └─ CR PseudoFlow (ops.example.com/v1alpha1)
       └─ Controller (kopf) → Kubernetes API
                              └─(опционально) Node Agent (DaemonSet) для node-level
```

- Контроллер подписан на Create/Update/Delete `PseudoFlow`.
- Исполнение шагов идемпотентное, последовательное по умолчанию, с поддержкой `parallel`.
- Для node-level действий применяется агент `pseudoflow-agent` (если шаги типа `execNode`, `configFile`, `patchFile` встречаются).

---

## 3. CRD

### 3.1. GVK
- `apiVersion`: `ops.example.com/v1alpha1`
- `kind`: `PseudoFlow`

### 3.2. Спецификация (сводно)
```yaml
spec:
  vars: { <string>: <string> }   # переменные для подстановки `${var}`
  steps:                         # массив шагов DSL
    - type: <string>
      ...                        # параметры зависят от типа шага
  options:
    concurrencyPolicy: Allow|Forbid|Replace  # дефолт: Allow
    timeoutSeconds: <int>                    # общий таймаут исполнения
status:
  observedGeneration: <int>
  lastRunTime: <RFC3339>
  phase: Succeeded|Failed|Running|Pending|Aborted
  message: <string>
  conditions:                                # стандартные Kubernetes Conditions
    - type: Ready|Progressing|Degraded
      status: "True"|"False"|"Unknown"
      reason: <string>
      message: <string>
      lastTransitionTime: <RFC3339>
```

### 3.3. Валидация (фрагмент OpenAPI v3 для CRD)
> Полный блок OpenAPI для каждого шага обширен; включены ключевые поля.
```yaml
# фрагмент для поля spec.vars и spec.steps[*].type
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
```

---

## 4. Безопасность и права
- Оператор: минимальные RBAC на чтение/запись CRD, чтение/патч целевых API ресурсов, создание/чтение Events.
- Агент: работает как DaemonSet с `hostNetwork: true`, требует ограниченный доступ к файловой системе и `systemctl` по design. Разрешения выдаются отдельно и минимально (Namespace `kube-system`).

---

## 5. Исполнение и идемпотентность
- Каждый шаг должен быть идемпотентен: повторное применение не должно ломать состояние.
- Поведение по ошибке:
  - По умолчанию `fail-fast`: останов. 
  - Переопределяется шагами `retry`, `onError`, флагом `continueOnError` у конкретного шага.
- Таймауты: на шаг и на весь Flow.
- Параллельность: `parallel` исполняет подмассив шагов конкурентно, `waitForAll: true|false`.

---

## 6. Шаблонизация и переменные
- Подстановка `${var}` во всех строковых полях шагов и в теле YAML.
- Источники переменных: `spec.vars`, результаты `exec/execNode/eval/template`.
- Защита: нет выполнения кода через подстановку, только строковые подмены.

---

## 7. DSL: перечень шагов и параметры

> Кратко. Реализация обязана валидировать входные поля и возвращать чёткие ошибки.

### 7.1 Базовые
- **log**: `{ message: <string> }`
- **sleep**: `{ seconds: <int> }`
- **apply**: `{ manifests: <string|YAML-multi-doc> }`
- **delete**: `{ target: { apiVersion, kind, name, namespace? } }`
- **applyFile**: `{ path: <string> }`
- **deleteFile**: `{ path: <string> }`
- **include**: `{ source: <http(s)://...|ConfigMapRef|SecretRef> }`

### 7.2 Условия
- **if**:
  ```yaml
  condition:
    resource: { apiVersion, kind, name, namespace? }
    jsonPath: <string>
    op: equals|notEquals|contains|greaterThan|lessThan
    value: <string>
  then: [steps...]
  else: [steps...]
  ```
- **when**: как `if`, но без ветвления: выполняется следующий шаг, если условие истинно.

### 7.3 Исполнение команд
- **exec**: `{ cmd: <string>, var?: <string>, container?: <string>, namespace?: <string> }`
  - Команда исполняется в поде оператора (или вспомогательном pod), stdout→`vars[var]`.
- **execNode**: `{ cmd: <string>, nodeSelector?: <labelSelector>, runOn?: all|any|first, varPerNode?: <string> }`
  - Выполняется агентом на нодах (DaemonSet). Результаты можно агрегировать.

### 7.4 Работа с файлами на ноде
- **configFile**: `{ path: <string>, content: <string>, mode?: "0644", owner?: "root:root" }`
- **patchFile**: `{ path: <string>, pattern: <regex|string>, replace: <string>, createIfMissing?: bool }`
- **template**: `{ output: <string>, template: <string> }`
- **script**: `{ code: <bash>, timeoutSeconds?: <int>, var?: <string> }`

### 7.5 Метаданные ресурсов
- **setLabel**:
  ```yaml
  target: { apiVersion?: <string>, kind: <string>, name?: <string>, namespace?: <string>, selector?: <labelSelector> }
  labels: { <k>: <v> }
  ```
- **removeLabel**: как `setLabel`, но `keys: [<labelKey>...]`
- **patchLabel**: `{ target: {...}, fromVar: <string> }` где переменная содержит словарь `"name" -> {"k":"v"}`.

### 7.6 Циклы и параллельность
- **loop**: `{ forEach: <expr|string>, steps: [ ... ] }` где `<expr>` формирует список.
- **loopNodes**: `{ selector: <labelSelector>, steps: [ ... ] }`
- **parallel**: `{ steps: [ [ ... ], [ ... ] ], waitForAll?: true }`

### 7.7 Ожидание
- **waitFor**:
  ```yaml
  resource: { apiVersion?:, kind:, name:, namespace?: }
  condition: Available|Ready|Healthy|Exist|Deleted|Custom
  jsonPath?: <string>, op?: <op>, value?: <string>   # для Custom
  timeoutSeconds?: <int>, intervalSeconds?: <int>
  ```

### 7.8 Управление ошибками
- **retry**: `{ steps: [ ... ], attempts: <int>, backoffSeconds: <int> }`
- **onError**: `{ steps: [ ... ] }` применяется к предыдущему шагу через связку.

### 7.9 Компоновка
- **includeFlow**: `{ name: <PseudoFlow name>, namespace?: <string>, inheritVars?: bool }`

---

## 8. Состояние, события, метрики

- **Status.Phase** обновляется пошагово.
- **Events**: на каждый шаг `Normal/Warning` с кратким сообщением.
- **Metrics (Prometheus)**:
  - `pseudoflow_runs_total{flow, status}`
  - `pseudoflow_step_duration_seconds{flow, step_type}`
  - `pseudoflow_active_flows`

---

## 9. Примеры сценариев из ваших руководств

### 9.1 NodeLocal DNSCache (на основе `nodelocaldns-setup.md`)

#### 9.1.1 Полный манифест DaemonSet/Service/ConfigMap (из вашего файла)
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nodelocaldns
  namespace: kube-system
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nodelocaldns
  namespace: kube-system
data:
  Corefile: |
    .:53 {
        errors
        cache {
            success 9984 30
            denial 9984 5
        }
        reload
        loop
        bind 100.64.0.10
        forward . 100.64.0.3 {
            force_tcp
        }
        prometheus :9253
        log
    }
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nodelocaldns
  namespace: kube-system
  labels:
    k8s-app: nodelocaldns
spec:
  selector:
    matchLabels:
      k8s-app: nodelocaldns
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        k8s-app: nodelocaldns
    spec:
      priorityClassName: system-cluster-critical
      serviceAccountName: nodelocaldns
      hostNetwork: true
      dnsPolicy: Default
      tolerations:
      - key: "CriticalAddonsOnly"
        operator: "Exists"
      - effect: "NoSchedule"
        key: node-role.kubernetes.io/control-plane
      - effect: "NoSchedule"
        key: node-role.kubernetes.io/master
      containers:
      - name: node-cache
        image: registry.k8s.io/dns/k8s-dns-node-cache:1.22.28
        args:
          - "-localip=100.64.0.10"
          - "-conf=/etc/Corefile"
          - "-upstreamtarget=100.64.0.3"
          - "-skipteardown=true"
          - "-setupinterface=true"
          - "-setupiptables=true"
        securityContext:
          privileged: true
        ports:
        - containerPort: 53
          hostPort: 53
          protocol: UDP
        - containerPort: 53
          hostPort: 53
          protocol: TCP
        - containerPort: 9253
          hostPort: 9253
          protocol: TCP
        resources:
          requests:
            cpu: 25m
            memory: 5Mi
          limits:
            memory: 200Mi
        volumeMounts:
        - name: config-volume
          mountPath: /etc/Corefile
          subPath: Corefile
        - name: xtables-lock
          mountPath: /run/xtables.lock
      volumes:
      - name: config-volume
        configMap:
          name: nodelocaldns
      - name: xtables-lock
        hostPath:
          path: /run/xtables.lock
          type: FileOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: nodelocaldns
  namespace: kube-system
spec:
  clusterIP: 100.64.0.10
  selector:
    k8s-app: nodelocaldns
  ports:
  - name: dns
    port: 53
    protocol: UDP
  - name: dns-tcp
    port: 53
    protocol: TCP
```

#### 9.1.2 ServiceMonitor (из вашего файла)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: nodelocaldns-metrics
  namespace: kube-system
  labels:
    k8s-app: nodelocaldns
spec:
  selector:
    k8s-app: nodelocaldns
  clusterIP: None
  ports:
    - name: metrics
      port: 9253
      targetPort: 9253
      protocol: TCP
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nodelocaldns
  namespace: kube-system
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      k8s-app: nodelocaldns
  namespaceSelector:
    matchNames:
      - kube-system
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
      relabelings:
        - sourceLabels: [__meta_kubernetes_pod_node_name]
          targetLabel: node
```

#### 9.1.3 Flow для автоматизации NodeLocal DNSCache
```yaml
apiVersion: ops.example.com/v1alpha1
kind: PseudoFlow
metadata:
  name: setup-nodelocaldns
  namespace: kube-system
spec:
  vars:
    dns_ip: "100.64.0.10"
    coredns_ip: "100.64.0.3"
  steps:
    - type: applyFile
      path: "nodelocaldns.yaml"
    - type: waitFor
      resource: { kind: DaemonSet, name: nodelocaldns, namespace: kube-system }
      condition: Available
      timeoutSeconds: 600
    - type: applyFile
      path: "servicemonitor-nodelocaldns.yaml"
    - type: loopNodes
      selector: ""
      steps:
        - type: configFile
          path: /etc/kubelet-resolv.conf
          content: |
            nameserver ${dns_ip}
            options ndots:5
            search cluster.local svc.cluster.local
        - type: patchFile
          path: /var/lib/kubelet/kubeadm-flags.env
          pattern: '--resolv-conf=[^" ]*'
          replace: '--resolv-conf=/etc/kubelet-resolv.conf'
          createIfMissing: false
        - type: execNode
          cmd: |
            systemctl daemon-reexec
            systemctl restart kubelet
```

---

### 9.2 kube-apiserver VIP через MetalLB и общесистемный доступ (на основе `kube-apiserver-haproxy-metallb.md`)

#### 9.2.1 Манифесты MetalLB IPAddressPool/L2Advertisement (из вашего файла)
```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: apiserver-pool
  namespace: metallb-system
spec:
  addresses:
    - 100.64.0.2-100.64.0.2
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: apiserver-announce
  namespace: metallb-system
```

#### 9.2.2 Service для kube-apiserver (из вашего файла)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: kube-apiserver-lb
  namespace: kube-system
spec:
  type: LoadBalancer
  loadBalancerIP: 100.64.0.2
  ports:
    - name: https
      port: 6443
      targetPort: 6443
      protocol: TCP
  selector:
    component: kube-apiserver
```

> Полный манифест DaemonSet HAProxy, упомянутый как `04-haproxy-autolb.yaml`, **не присутствует** в предоставленных материалах. Поэтому он не включён. Оператор может применить его через `applyFile/include`, если файл будет добавлен в репозиторий артефактов.

#### 9.2.3 Flow для автоматизации MetalLB + перевода kubeconfig
```yaml
apiVersion: ops.example.com/v1alpha1
kind: PseudoFlow
metadata:
  name: setup-apiserver-vip
  namespace: kube-system
spec:
  vars:
    vip: "100.64.0.2"
  steps:
    - type: applyFile
      path: "01-metallb-apiserver.yaml"
    - type: waitFor
      resource: { apiVersion: "metallb.io/v1beta1", kind: IPAddressPool, name: apiserver-pool, namespace: metallb-system }
      condition: Exist
    - type: applyFile
      path: "02-kube-apiserver-lb-svc.yaml"
    - type: waitFor
      resource: { kind: Service, name: kube-apiserver-lb, namespace: kube-system }
      condition: Exist
    - type: parallel
      waitForAll: true
      steps:
        - - type: loopNodes
            selector: "node-role.kubernetes.io/control-plane"
            steps:
              - type: patchFile
                path: /etc/kubernetes/kubelet.conf
                pattern: 'server: https://.*:6443'
                replace: 'server: https://${vip}:6443'
              - type: patchFile
                path: /etc/kubernetes/controller-manager.conf
                pattern: 'server: https://.*:6443'
                replace: 'server: https://${vip}:6443'
              - type: patchFile
                path: /etc/kubernetes/scheduler.conf
                pattern: 'server: https://.*:6443'
                replace: 'server: https://${vip}:6443'
              - type: execNode
                cmd: |
                  systemctl daemon-reexec
                  systemctl restart kubelet
        - - type: loopNodes
            selector: "!node-role.kubernetes.io/control-plane"
            steps:
              - type: patchFile
                path: /etc/kubernetes/kubelet.conf
                pattern: 'server: https://.*:6443'
                replace: 'server: https://${vip}:6443'
              - type: execNode
                cmd: |
                  systemctl daemon-reexec
                  systemctl restart kubelet
```

---

## 10. Работа с labels из вывода команд

### Пример: добавить label на все ноды без `zone`
```yaml
steps:
  - type: exec
    cmd: "kubectl get nodes -l '!zone' -o jsonpath='{.items[*].metadata.name}'"
    var: unlabeled
  - type: loop
    forEach: "${unlabeled.split(' ')}"
    steps:
      - type: setLabel
        target: { kind: Node, name: "${item}" }
        labels: { zone: "auto" }
```

### Пример: массовая правка labels из переменной
```yaml
vars:
  mapping: |
    {"node1":{"env":"stage"},"node2":{"env":"prod"}}
steps:
  - type: eval
    expression: "json(${mapping})"   # результат → vars._map
    var: _map
  - type: patchLabel
    target: { kind: Node, selector: "" }
    fromVar: _map
```

> Примечание: шаг `eval` используется только для безопасных выражений трансформации строк/JSON, без внешнего кода.

---

## 11. Развёртывание

- CRD, RBAC, Deployment оператора
- Опционально: DaemonSet `pseudoflow-agent`

Каталоги Helm-чарта:
```
charts/pseudoflow-operator/
  templates/
    crd-pseudoflow.yaml
    rbac.yaml
    deployment.yaml
    servicemonitor.yaml
    agent-daemonset.yaml
  values.yaml
```

---

## 12. Наблюдаемость и алерты
- ServiceMonitor для оператора и агента.
- Рекомендуемые алерты:
  - `PseudoflowFailedRunsHigh` — процент неуспешных запусков > X% за 15м.
  - `PseudoflowLongRunning` — длительность шага > порога.

---

## 13. Тестирование

### 13.1 Unit
- Парсер DSL, подстановка переменных, планировщик шагов, backoff.

### 13.2 E2E
- Minikube/kind. Сценарии:
  - Применение/удаление NLDNS манифеста.
  - Патч kubelet.conf на нодах (через агент-симулятор).
  - Метки на нодах из `exec`.

### 13.3 Идемпотентность
- Повторный запуск одинаковых flows не меняет состояние.

---

## 14. Обновления и откаты
- Контролируем через образ Deployment оператора.
- CRD версионирование `v1alpha1 → v1beta1` с конверсионным webhook при необходимости.
- Для node-level изменений предусмотрены обратные шаги (`deleteFile`, обратные `patchFile`).

---

## 15. Ограничения
- Без агента недоступны `execNode`, `configFile`, `patchFile`, `script`.
- Нельзя гарантировать консистентность при внешних ручных изменениях вне DSL.
- Полный манифест HAProxy DaemonSet не включён, так как отсутствовал в предоставленных документах.

---

## 16. Лицензия и репозиторий
- MIT
- GitHub: `github.com/<org>/pseudoflow-operator`
- CI: flake8, build, push GHCR

```

