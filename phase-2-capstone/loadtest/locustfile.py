"""Load test for the inference platform — drives traffic so you can watch the
system saturate, KEDA scale out, and TTFT degrade under pressure.

Run:
    pip install locust
    locust -f locustfile.py --host http://<gateway-or-service>/v1

Then open http://localhost:8089 and ramp users up. Watch your Grafana TTFT p95
and the replica count (kubectl get deploy -w) at the same time — the goal is to
*see* the autoscaler react to an inference-aware signal, then write up where it
saturates and the cost-per-million-tokens at that point.
"""
import os
import time

from locust import HttpUser, task, between

MODEL = os.environ.get("MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
PROMPT = "Summarize the trade-offs between throughput and latency in LLM serving."


class InferenceUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task
    def chat(self):
        start = time.perf_counter()
        ttft = None
        with self.client.post(
            "/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 200,
                "stream": True,
            },
            stream=True,
            catch_response=True,
            name="chat.completions",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            for line in resp.iter_lines():
                if line and ttft is None:
                    ttft = time.perf_counter() - start
            # Record TTFT as a custom metric so it shows in the Locust UI.
            self.environment.events.request.fire(
                request_type="TTFT",
                name="time_to_first_token",
                response_time=(ttft or 0) * 1000,
                response_length=0,
                exception=None,
                context={},
            )
            resp.success()
