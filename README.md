# LLM Deploy · 大模型部署推理管理平台

把模型仓库、部署编排、在线推理与可观测性收在一处的管理平台。
后端 FastAPI + SQLite，前端 React + TypeScript + Ant Design，**零外部依赖即可完整跑通**。

```
┌─────────────┐   REST/SSE    ┌──────────────────────────────────────┐
│  React 控制台 │ ────────────▶ │  FastAPI                             │
│  模型/部署/   │               │  ├─ 路由层  鉴权 · 校验               │
│  测试台/监控  │ ◀──────────── │  ├─ 编排器  状态机 · 端口 · 巡检       │
└─────────────┘               │  └─ 引擎层  mock │ openai │ vllm …    │
                              └───────────────┬──────────────────────┘
                                              │ OpenAI 兼容
                              ┌───────────────▼──────────────────────┐
                              │ 推理实例（Mock / vLLM / Ollama / …）  │
                              └──────────────────────────────────────┘
```

## 快速开始

```bash
# 1. 后端依赖
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 前端依赖
cd ../frontend && npm install

# 3. 一键构建前端并启动（在仓库根目录）
cd .. && backend/.venv/bin/python start.py
```

打开 <http://127.0.0.1:8000>，用 **admin / admin123** 登录。

> 只想跑后端：`cd backend && .venv/bin/python -m uvicorn app.main:app --reload`
> 前端热更新开发：`cd frontend && npm run dev`（已配置代理到 8000 端口）

首次启动会自动建库、写入管理员账号与 4 个示例模型。

## 功能

| 模块 | 能力 |
| --- | --- |
| **总览** | 模型/部署/请求量/延迟/成功率大盘，运行中实例一览 |
| **模型仓库** | 模型登记与检索，支持 HuggingFace / ModelScope / 本地目录三种来源 |
| **部署管理** | 创建即启动、启停、重启、删除；状态机与事件时间线；动态参数表单 |
| **推理测试台** | 对话与文本补全两种模式，支持流式输出、温度/长度调节、系统提示词 |
| **监控** | QPS、吞吐、P50/P95 延迟、GPU 利用率与显存时序曲线（5 秒采样） |
| **请求日志** | 每次调用的 token 计量、耗时、状态与错误，可按部署与状态筛选 |
| **API Key** | 独立于登录态的调用凭证，支持启停与删除，明文仅展示一次 |

## 推理引擎（可插拔）

引擎层是本平台的核心抽象。编排器只依赖 `InferenceEngine` 接口，不认识具体实现：

```
backend/app/engines/
├── base.py            # 抽象接口：start/stop/health/complete/stream/metrics
├── __init__.py        # 注册表：@register_engine 装饰器
├── mock.py            # 内置仿真引擎（默认，无需 GPU）
├── openai_compat.py   # OpenAI 兼容服务（vLLM/Ollama/TGI/SGLang/LM Studio）
└── vllm.py            # vLLM 子进程编排 + 指标解析
```

| 引擎 | 说明 | GPU |
| --- | --- | --- |
| `mock` | 仿真引擎，按提示词生成占位回复并模拟吞吐/延迟/显存曲线 | 否 |
| `openai` | 对接任意 OpenAI 兼容服务，地址与密钥可配 | 否 |
| `vllm` | 执行 `vllm serve` 拉起真实模型实例，复用 OpenAI 客户端推理 | 是 |

`vllm` 引擎在本机未安装 vLLM 时会标记为「不可用」，但代码路径完整 —— 换到 GPU 机器上
`pip install vllm` 后无需改动任何平台代码即可选它部署真实模型。

**新增一个引擎**只需实现接口并注册，前端表单会根据引擎自描述的 `param_schema` 自动渲染：

```python
from . import register_engine
from .base import InferenceEngine

@register_engine
class MyEngine(InferenceEngine):
    name = "my-engine"
    display_name = "我的引擎"
    default_params = {"foo": 1}
    param_schema = [{"key": "foo", "label": "参数", "type": "int", "default": 1}]

    async def start(self, ctx): ...
    async def stop(self, ctx): ...
    async def health(self, ctx): ...
    async def complete(self, ctx, request): ...
    async def stream(self, ctx, request): ...
    async def metrics(self, ctx): ...
```

## 对外推理接口

除控制台外，平台暴露 **OpenAI 兼容** 接口，可直接替换 OpenAI SDK 的 `base_url`：

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="sk-llmd-...")

# 非流式
resp = client.chat.completions.create(
    model="qwen7b-prod",              # 这里填「部署名称」
    messages=[{"role": "user", "content": "你好"}],
)

# 流式
for chunk in client.chat.completions.create(
    model="qwen7b-prod",
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="")
```

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-llmd-..." \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen7b-prod","messages":[{"role":"user","content":"你好"}]}'
```

已支持 `GET /v1/models`、`POST /v1/chat/completions`、`POST /v1/completions`，
流式为标准 OpenAI 分片格式（`chat.completion.chunk` + `[DONE]`）。

## 项目结构

```
infra/
├── start.py                  # 一键构建前端 + 启动服务
├── backend/
│   ├── requirements.txt
│   ├── data/                 # SQLite 与模型目录（自动创建，不入库）
│   ├── tests/test_api.py     # 22 项端到端测试
│   └── app/
│       ├── main.py           # 应用入口、初始化、SPA 挂载
│       ├── config.py         # LLMD_* 环境变量配置
│       ├── db.py             # 引擎与会话
│       ├── models.py         # ORM：用户/模型/部署/事件/指标/日志/密钥
│       ├── schemas.py        # 出入参模型
│       ├── security.py       # PBKDF2 密码、JWT、API Key
│       ├── orchestrator.py   # 部署编排、推理调度、后台巡检
│       ├── engines/          # 可插拔推理引擎
│       └── routers/          # auth/models/deployments/inference/metrics/keys/overview
└── frontend/
    └── src/
        ├── api/              # 类型定义与接口封装
        ├── hooks/            # useAuth / usePolling / useStream
        ├── layouts/          # 侧边栏布局
        ├── components/       # 状态标签、引擎参数动态表单
        └── pages/            # 总览/模型/部署/详情/测试台/日志/密钥/登录
```

## 配置

全部通过环境变量或 `backend/.env` 覆盖，前缀 `LLMD_`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLMD_DATA_DIR` | `backend/data` | 数据目录 |
| `LLMD_SECRET_KEY` | `dev-secret-change-me…` | JWT 签名密钥，**生产必须修改** |
| `LLMD_BOOTSTRAP_ADMIN_PASSWORD` | `admin123` | 初始管理员密码 |
| `LLMD_DEFAULT_ENGINE` | `mock` | 默认引擎 |
| `LLMD_PORT_RANGE_START/END` | `8100/8199` | 实例端口分配区间 |
| `LLMD_HEALTH_CHECK_INTERVAL_SECONDS` | `5` | 健康巡检与指标采样周期 |
| `LLMD_CORS_ORIGINS` | `localhost:5173` | 允许的前端来源 |

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

覆盖认证与越权、模型 CRUD、部署状态机（创建/停止/重启、重名与占用冲突）、
非流式与流式推理、SSE 分片格式回归、指标采集、请求日志、API Key 与 OpenAI 兼容入口。

## 已知边界

这是用于学习与验证的**完整骨架**，生产化前还需补齐：

- **认证**：仅单角色（管理员/普通用户），无 RBAC、无审计日志
- **多租户**：所有用户共享同一资源池，无配额与计费
- **调度**：`replicas` 字段已预留，但未实现真实的横向扩缩容与负载均衡
- **持久化**：SQLite 适合单机；多实例部署需切换 PostgreSQL
- **密钥**：部署参数中的 `api_key` 目前明文存于 JSON 字段，生产应接密钥管理服务
- **前端**：未做路由级代码分割，antd 分包后仍有约 360 kB（gzip）
