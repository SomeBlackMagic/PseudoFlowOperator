
# PseudoFlow Operator — MVP

Функционал:
- CRD `ops.example.com/v1alpha1, PseudoFlow`
- Шаги: `log, sleep, apply, delete, waitFor{Exist,Deleted,Ready}, setLabel, removeLabel, loop, parallel`
- Шаблоны `${var}`

Запуск:
```sh
kubectl apply -f deploy/crd_pseudoflow.yaml
kubectl apply -f deploy/rbac.yaml
# соберите образ и поправьте image в deployment.yaml
kubectl apply -f deploy/deployment.yaml
```
