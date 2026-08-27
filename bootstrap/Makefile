# Thin wrapper around platform.sh.
# On the k3s server run with:  make up KUBECTL="k3s kubectl"
SH := ./platform.sh

.PHONY: up down status prereqs platform netfix serving autoscaling gitops gateway \
        down-gateway down-gitops down-autoscaling down-serving down-platform down-prereqs

up:               ; $(SH) up
down:             ; $(SH) down
status:           ; $(SH) status

prereqs:          ; $(SH) prereqs         ## NVIDIA device plugin + GPU exporter
platform:         ; $(SH) platform        ## cert-manager + KEDA + KServe
netfix:           ; $(SH) netfix          ## WSL2 overlay workarounds
serving:          ; $(SH) serving         ## vLLM two-GPU + Service/PodMonitor/SLO/dashboard
autoscaling:      ; $(SH) autoscaling     ## KEDA ScaledObject
gitops:           ; $(SH) gitops          ## Argo CD + Applications
gateway:          ; $(SH) gateway         ## Envoy AI Gateway

down-gateway:     ; $(SH) down-gateway
down-gitops:      ; $(SH) down-gitops
down-autoscaling: ; $(SH) down-autoscaling
down-serving:     ; $(SH) down-serving
down-platform:    ; $(SH) down-platform
down-prereqs:     ; $(SH) down-prereqs
