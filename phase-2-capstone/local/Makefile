CLUSTER ?= inference-platform
IMAGE   ?= mock-vllm:local

.PHONY: up cluster keda monitoring image deploy status watch port-forward load grafana prometheus down

## up: create the cluster and bring up the whole stack
up: cluster keda monitoring image deploy dashboard
	@echo ""
	@echo "Stack is up. In separate terminals:"
	@echo "  make port-forward   # expose the service on :8000"
	@echo "  make load           # drive traffic with locust"
	@echo "  make watch          # watch KEDA scale the deployment"
	@echo "  make grafana        # dashboards at http://localhost:3000 (admin/admin)"

cluster:
	kind create cluster --name $(CLUSTER) --config kind-config.yaml

keda:
	helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
	helm repo update >/dev/null
	helm upgrade --install keda kedacore/keda -n keda --create-namespace --wait

monitoring:
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
	helm repo update >/dev/null
	helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
		-n monitoring --create-namespace --wait --timeout 10m \
		--set grafana.adminPassword=admin

## image: build the mock and side-load it into the kind node
image:
	docker build -t $(IMAGE) mock-vllm
	kind load docker-image $(IMAGE) --name $(CLUSTER)

deploy:
	kubectl apply -f manifests/

## dashboard: load the Grafana dashboard as a sidecar-watched ConfigMap
dashboard:
	kubectl create configmap inference-dashboard -n monitoring \
		--from-file=inference-dashboard.json=grafana/inference-dashboard.json \
		--dry-run=client -o yaml | kubectl apply -f -
	kubectl label configmap inference-dashboard grafana_dashboard=1 -n monitoring --overwrite

## status / watch: see the autoscaler and replicas
status:
	kubectl get deploy,scaledobject,hpa,pods -n inference

watch:
	kubectl get deploy/mock-vllm,hpa -n inference -w

port-forward:
	kubectl -n inference port-forward svc/mock-vllm 8000:8000

## load: drive traffic (needs `make port-forward` running in another terminal)
load:
	cd ../loadtest && locust -f locustfile.py --host http://localhost:8000/v1

grafana:
	@echo "Grafana: http://localhost:3000  (admin / admin)"
	kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80

prometheus:
	@echo "Prometheus: http://localhost:9090"
	kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090

## down: delete the whole cluster
down:
	kind delete cluster --name $(CLUSTER)
