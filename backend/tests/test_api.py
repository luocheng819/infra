"""端到端测试：覆盖认证、模型仓库、部署生命周期、推理与监控。

运行：``.venv/bin/python -m pytest tests -q``
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# 必须在导入 app 之前设置，保证测试使用独立的数据目录
_TMP = tempfile.mkdtemp(prefix="llmd-test-")
os.environ["LLMD_DATA_DIR"] = _TMP
os.environ["LLMD_BOOTSTRAP_ADMIN_PASSWORD"] = "test123456"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    _ = Path(_TMP)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "test123456"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
def test_health(client: TestClient):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_rejects_bad_password(client: TestClient):
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_protected_route_requires_token(client: TestClient):
    assert client.get("/api/models").status_code == 401


def test_me(client: TestClient, headers: dict):
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["is_admin"] is True


# --------------------------------------------------------------------------- #
# 模型仓库
# --------------------------------------------------------------------------- #
def test_seeded_models_are_listed(client: TestClient, headers: dict):
    resp = client.get("/api/models", headers=headers)
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()}
    assert "qwen2.5-7b-instruct" in names


def test_model_crud(client: TestClient, headers: dict):
    created = client.post(
        "/api/models",
        headers=headers,
        json={
            "name": "pytest-demo",
            "display_name": "Pytest 演示模型",
            "source": "huggingface",
            "source_ref": "demo/model",
            "tags": ["测试"],
        },
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]

    # 重名应被拒绝
    dup = client.post(
        "/api/models",
        headers=headers,
        json={
            "name": "pytest-demo",
            "display_name": "重复",
            "source": "huggingface",
            "source_ref": "demo/model",
        },
    )
    assert dup.status_code == 409

    patched = client.patch(
        f"/api/models/{model_id}", headers=headers, json={"description": "已更新"}
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "已更新"

    assert client.delete(f"/api/models/{model_id}", headers=headers).status_code == 204
    assert client.get(f"/api/models/{model_id}", headers=headers).status_code == 404


def test_search_models(client: TestClient, headers: dict):
    resp = client.get("/api/models", headers=headers, params={"q": "Qwen"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


# --------------------------------------------------------------------------- #
# 引擎目录
# --------------------------------------------------------------------------- #
def test_engine_catalog(client: TestClient, headers: dict):
    resp = client.get("/api/engines", headers=headers)
    assert resp.status_code == 200
    by_name = {e["name"]: e for e in resp.json()}
    assert {"mock", "openai", "vllm"} <= set(by_name)
    assert by_name["mock"]["available"] is True
    assert by_name["mock"]["param_schema"]


# --------------------------------------------------------------------------- #
# 部署生命周期 + 推理
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def deployment(client: TestClient, headers: dict) -> dict:
    models = client.get("/api/models", headers=headers).json()
    model_id = next(m["id"] for m in models if m["name"] == "qwen2.5-7b-instruct")
    resp = client.post(
        "/api/deployments",
        headers=headers,
        json={
            "name": "pytest-deploy",
            "model_id": model_id,
            "engine": "mock",
            "engine_params": {"simulated_tps": 500},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "running", body
    assert body["host_port"] is not None
    return body


def test_deployment_is_running(client: TestClient, headers: dict, deployment: dict):
    resp = client.get(f"/api/deployments/{deployment['id']}", headers=headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["status"] == "running"
    # 生命周期事件应被记录
    assert any(e["event"] == "started" for e in detail["events"])


def test_duplicate_deployment_name_rejected(
    client: TestClient, headers: dict, deployment: dict
):
    resp = client.post(
        "/api/deployments",
        headers=headers,
        json={
            "name": deployment["name"],
            "model_id": deployment["model_id"],
            "engine": "mock",
        },
    )
    assert resp.status_code == 409


def test_deployment_health_endpoint(client: TestClient, headers: dict, deployment: dict):
    resp = client.get(f"/api/deployments/{deployment['id']}/health", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["healthy"] is True


def test_completion(client: TestClient, headers: dict, deployment: dict):
    resp = client.post(
        f"/api/inference/{deployment['id']}/completions",
        headers=headers,
        json={"prompt": "介绍一下你自己", "max_tokens": 64},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["text"]
    assert body["usage"]["completion_tokens"] > 0


def test_chat_non_stream(client: TestClient, headers: dict, deployment: dict):
    resp = client.post(
        f"/api/inference/{deployment['id']}/chat/completions",
        headers=headers,
        json={
            "messages": [
                {"role": "system", "content": "你是运维助手"},
                {"role": "user", "content": "如何查看部署状态？"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"]
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_chat_stream(client: TestClient, headers: dict, deployment: dict):
    with client.stream(
        "POST",
        f"/api/inference/{deployment['id']}/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "流式测试"}], "stream": True},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert "event: delta" in text
    assert "event: done" in text


def test_logs_recorded(client: TestClient, headers: dict, deployment: dict):
    resp = client.get(f"/api/deployments/{deployment['id']}/logs", headers=headers)
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 2
    assert any(log["status"] == "success" for log in logs)


def test_metrics_collected(client: TestClient, headers: dict, deployment: dict):
    import time

    # 后台巡检按 health_check_interval 采样，等一轮
    time.sleep(6)
    resp = client.get(f"/api/deployments/{deployment['id']}/metrics", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["samples"], "应至少有一个指标采样点"
    assert summary["current"]["gpu_memory_total_mb"] > 0


def test_overview(client: TestClient, headers: dict, deployment: dict):
    resp = client.get("/api/overview", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_models"] >= 4
    assert body["running_deployments"] >= 1
    assert body["total_requests"] >= 2


# --------------------------------------------------------------------------- #
# API Key 与 OpenAI 兼容入口
# --------------------------------------------------------------------------- #
def test_api_key_flow(client: TestClient, headers: dict, deployment: dict):
    created = client.post("/api/keys", headers=headers, json={"name": "测试用 Key"})
    assert created.status_code == 201, created.text
    raw = created.json()["key"]
    assert raw.startswith("sk-llmd-")

    # 无 key 应被拒绝
    assert client.get("/v1/models").status_code == 401

    listed = client.get("/v1/models", headers={"Authorization": f"Bearer {raw}"})
    assert listed.status_code == 200
    assert any(m["id"] == deployment["name"] for m in listed.json()["data"])

    chat = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {raw}"},
        json={
            "model": deployment["name"],
            "messages": [{"role": "user", "content": "OpenAI 兼容入口测试"}],
        },
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["choices"][0]["message"]["content"]
    assert chat.json()["object"] == "chat.completion"


def test_api_key_toggle(client: TestClient, headers: dict):
    key_id = client.get("/api/keys", headers=headers).json()[0]["id"]
    assert client.post(f"/api/keys/{key_id}/toggle", headers=headers).status_code == 200
    assert client.post(f"/api/keys/{key_id}/toggle", headers=headers).status_code == 200


def test_openai_compatible_stream_format(client: TestClient, headers: dict, deployment: dict):
    """回归：/v1 的流式必须是 OpenAI 分片格式，否则官方 SDK 解析不到任何增量。"""
    import json

    key = client.post("/api/keys", headers=headers, json={"name": "流式回归"}).json()["key"]
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": deployment["name"],
            "messages": [{"role": "user", "content": "分片格式回归"}],
            "stream": True,
        },
    ) as resp:
        assert resp.status_code == 200
        frames = [
            line[6:]
            for line in resp.iter_lines()
            if line.startswith("data: ")
        ]

    assert frames[-1] == "[DONE]", frames[-1]

    payloads = [json.loads(f) for f in frames[:-1]]
    assert all(p["object"] == "chat.completion.chunk" for p in payloads)
    # 首个分片携带 role，其余携带 content
    assert payloads[0]["choices"][0]["delta"] == {"role": "assistant"}
    content = "".join(
        p["choices"][0]["delta"].get("content", "") for p in payloads
    )
    assert content, "流式必须产出实际内容"
    # 结束分片带 finish_reason 与 usage
    assert payloads[-1]["choices"][0]["finish_reason"] == "stop"
    assert "usage" in payloads[-1]


# --------------------------------------------------------------------------- #
# 部署状态机收尾
# --------------------------------------------------------------------------- #
def test_stop_and_restart(client: TestClient, headers: dict, deployment: dict):
    did = deployment["id"]
    stopped = client.post(f"/api/deployments/{did}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    # 停止后不应对接推理
    denied = client.post(
        f"/api/inference/{did}/completions",
        headers=headers,
        json={"prompt": "应当失败"},
    )
    assert denied.status_code == 409

    restarted = client.post(f"/api/deployments/{did}/restart", headers=headers)
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "running"


def test_cannot_delete_model_with_running_deployment(
    client: TestClient, headers: dict, deployment: dict
):
    resp = client.delete(f"/api/models/{deployment['model_id']}", headers=headers)
    assert resp.status_code == 409
