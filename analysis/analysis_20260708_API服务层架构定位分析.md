# 分析：API 服务层的架构定位与目录归属（2026-07-08）

## 1. 问题本质

**一句话**：API 服务层（认证、任务管理、路由）是一个**独立的服务框架**，还是核心 OCR 库的**附属模块**？

**核心矛盾**：
- 当前 API 代码在 `demo/api/`，与 Demo 调试代码混在一起 → 职责不清
- 用户要求 auth.py、task_manager.py 独立可复用 → 需要脱离 OCR 核心包
- `src/ocr_three_layer_hybrid/` 是纯库（零 HTTP 依赖）→ 混入 FastAPI 会破坏这个特性

---

## 2. 现状分析

### 2.1 依赖关系

```
src/ocr_three_layer_hybrid/   ← 纯 OCR 库，零 HTTP 依赖 ✅
    └── (无 fastapi / uvicorn / starlette)

demo/api/                     ← API 服务层，依赖 FastAPI
    ├── auth.py        (164 行) ← 不依赖 OCRService ✅ 可复用
    ├── task_manager.py (481 行) ← 不依赖 OCRService ✅ 可复用
    ├── schemas.py     (115 行) ← 不依赖 OCRService ✅ 可复用
    └── routes/
        ├── health.py          ← 注入 OCRService 实例（构造函数）
        ├── ocr.py             ← 注入 OCRService 实例（构造函数）
        ├── task.py            ← 不依赖 OCRService ✅
        └── quota.py           ← 不依赖 OCRService ✅
```

**关键发现**：
- **基础设施层**（auth + task_manager + schemas = 760 行）与 OCR **完全解耦**
- **路由层**（4 个路由文件）通过构造函数注入 OCRService，是唯一的耦合点
- OCR 核心包保持纯净，不需要引入任何 HTTP 框架

### 2.2 复用需求

用户明确要求：
> "API认证（可能还有鉴权和参数签名）、任务持久化等功能要在架构时独立、方便其他项目复用"

这意味着：
- `auth.py` → 应能被其他项目 `import` 而不引入 OCR 依赖
- `task_manager.py` → 应能管理任何异步任务，不限于 OCR
- `schemas.py` → 通用响应格式，可被其他 API 复用

---

## 3. 方案对比

### 方案 A：API 放在 `src/ocr_three_layer_hybrid/api/`

```
src/ocr_three_layer_hybrid/
├── pipeline.py
├── service.py
├── classifier.py
├── ...
└── api/                    ← 新增
    ├── auth.py
    ├── task_manager.py
    ├── schemas.py
    └── routes/
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 包纯洁性 | 🔴 差 | OCR 库被迫依赖 FastAPI/uvicorn |
| 复用性 | 🔴 差 | `import ocr_three_layer_hybrid.api.auth` 需要整个 OCR 包 |
| 职责分离 | 🔴 差 | 库 vs 服务混在一起 |
| 导入路径 | 🟡 中 | 路径太长 |
| 独立部署 | 🔴 差 | 无法独立部署 API 服务 |

**结论：不推荐**。违反单一职责，破坏核心包的纯洁性。

### 方案 B：API 放在根目录 `api/`

```
api/                        ← 新增顶层目录
├── auth.py
├── task_manager.py
├── schemas.py
└── routes/
src/ocr_three_layer_hybrid/ ← 不变
demo/                       ← 不变
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 包纯洁性 | 🟢 好 | OCR 库不受影响 |
| 复用性 | 🔴 差 | 根目录包导入不优雅，需要 sys.path |
| 职责分离 | 🟢 好 | 完全独立 |
| 导入路径 | 🔴 差 | `from api.auth import ...` 不标准 |
| 独立部署 | 🟡 中 | 可以独立但缺少标准 Python 包结构 |

**结论：不推荐**。根目录不是放 Python 包的标准位置。

### 方案 C：API 作为独立包 `src/ocr_api/`（✅ 推荐）

```
src/
├── ocr_three_layer_hybrid/   ← 纯 OCR 库（不变）
└── ocr_api/                  ← 新增：独立 API 服务包
    ├── __init__.py
    ├── common/               ← 通用服务基础设施（可复用）
    │   ├── __init__.py
    │   ├── auth.py           ← API Key 认证
    │   ├── schemas.py        ← 统一响应模型
    │   └── task_manager.py   ← 异步任务管理
    └── ocr/                  ← OCR 业务路由
        ├── __init__.py
        ├── routes/
        │   ├── health.py
        │   ├── ocr.py
        │   ├── task.py
        │   └── quota.py
        └── server.py         ← FastAPI 入口
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 包纯洁性 | 🟢 好 | OCR 库不受影响 |
| 复用性 | 🟢 好 | `from ocr_api.common.auth import APIKeyAuthenticator` |
| 职责分离 | 🟢 好 | common（通用）与 ocr（业务）清晰分层 |
| 导入路径 | 🟢 好 | 标准 Python 包路径 |
| 独立部署 | 🟢 好 | 可独立打包、独立 pip install |
| 可扩展性 | 🟢 好 | 新增其他业务只需加 `src/ocr_api/xxx/` |

**结论：推荐**。既保持独立又方便复用。

### 方案 D：拆成两个包 `src/ocr_service_common/` + `src/ocr_api/`

```
src/
├── ocr_three_layer_hybrid/   ← 纯 OCR 库
├── ocr_service_common/       ← 通用服务基础设施
│   ├── auth.py
│   ├── schemas.py
│   └── task_manager.py
└── ocr_api/                  ← OCR API 服务
    ├── routes/
    └── server.py
```

| 维度 | 评估 | 说明 |
|------|------|------|
| 复用性 | 🟢 最好 | common 可以完全独立发布 |
| 复杂度 | 🔴 高 | 多一个包，多一层维护 |
| 当前需求 | 🟡 过度 | 目前只有 OCR 一个业务，不需要拆这么细 |

**结论：过度设计**。当前阶段不需要，未来用户多了再考虑。

---

## 4. 苏格拉底提问

**Q1: API 的本质是什么？**
A: API 是 OCR 库的**服务化包装**——它不是一个库，而是一个**可部署的服务**。它有自己的生命周期（HTTP 端口、认证、任务队列），与 OCR 库是「消费者-提供者」关系，不是包含关系。

**Q2: 如果其他项目要用 auth.py，应该怎么做？**
A: 理想情况：`pip install ocr-api` 或直接把 `src/ocr_api/common/` 复制走。不应要求对方先安装整个 OCR 包。

**Q3: 放在 src/ 下 vs 根目录，有什么区别？**
A: `src/` 是 Python 标准的包目录，配合 `pyproject.toml` / `setup.py` 可以一行 `pip install -e .` 安装。根目录的 `api/` 不是标准做法，需要手动配置 `sys.path` 或 `PYTHONPATH`。

**Q4: common/ 和 ocr/ 分层的必要性？**
A: 必要。`auth.py` 和 `task_manager.py` 不依赖 OCR，是**通用基础设施**。`routes/ocr.py` 依赖 OCRService，是**业务逻辑**。分层后：
- 其他项目可以只拿走 `common/` 不碰 `ocr/`
- 未来新增其他业务（如 `invoice_api/`）可以复用 `common/`

**Q5: server.py 放在哪里？**
A: 放在 `ocr_api/ocr/server.py`。它是 OCR API 的启动入口，属于 OCR 业务层。如果需要，也可以保留根目录的 `demo/server.py` 作为调试入口。

---

## 5. 推荐方案：方案 C

### 最终目录结构

```
src/
├── ocr_three_layer_hybrid/          ← 纯 OCR 库（不变）
│   ├── __init__.py
│   ├── classifier.py
│   ├── config.py
│   ├── pipeline.py
│   ├── service.py
│   ├── ...
│   └── extractors/
│
└── ocr_api/                         ← 🆕 独立 API 服务包
    ├── __init__.py                  ← 版本号、导出
    │
    ├── common/                      ← 🆕 通用服务基础设施（可复用）
    │   ├── __init__.py
    │   ├── auth.py                  ← 认证/鉴权/签名（164 行）
    │   ├── schemas.py               ← 统一响应模型（115 行）
    │   └── task_manager.py          ← 异步任务管理 SQLite（481 行）
    │
    └── ocr/                         ← OCR 业务层
        ├── __init__.py
        ├── server.py                ← FastAPI 主入口
        ├── ocr_service.py           ← OCRService 兼容层
        ├── baseline_service.py      ← 基线数据服务
        ├── debug_routes.py          ← 调试路由（DEBUG=true）
        ├── routes/                  ← API 路由
        │   ├── __init__.py
        │   ├── health.py            ← GET /health
        │   ├── ocr.py               ← POST /api/v1/ocr/async
        │   ├── task.py              ← GET/POST task 管理
        │   └── quota.py             ← GET /api/v1/quota
        ├── static/                  ← Demo 前端
        │   ├── css/demo.css
        │   └── js/
        └── templates/
            └── index.html
```

### 复用方式

```python
# 其他项目复用认证模块
from ocr_api.common.auth import APIKeyAuthenticator

# 其他项目复用任务管理
from ocr_api.common.task_manager import TaskManager, TaskWorker

# 其他项目复用响应模型
from ocr_api.common.schemas import APIResponse, APIErrorResponse
```

### 迁移计划

| 步骤 | 操作 | 文件 |
|------|------|------|
| 1 | 创建 `src/ocr_api/common/` | 新建目录 |
| 2 | 移动通用组件 | `demo/api/auth.py` → `src/ocr_api/common/auth.py` |
|   |  | `demo/api/task_manager.py` → `src/ocr_api/common/task_manager.py` |
|   |  | `demo/api/schemas.py` → `src/ocr_api/common/schemas.py` |
| 3 | 创建 `src/ocr_api/ocr/` | 新建目录 |
| 4 | 移动路由 | `demo/api/routes/` → `src/ocr_api/ocr/routes/` |
| 5 | 移动服务文件 | `demo/server.py` → `src/ocr_api/ocr/server.py` |
|   |  | `demo/debug_routes.py` → `src/ocr_api/ocr/debug_routes.py` |
|   |  | `demo/ocr_service.py` → `src/ocr_api/ocr/ocr_service.py` |
|   |  | `demo/baseline_service.py` → `src/ocr_api/ocr/baseline_service.py` |
| 6 | 移动前端资源 | `demo/static/` → `src/ocr_api/ocr/static/` |
|   |  | `demo/templates/` → `src/ocr_api/ocr/templates/` |
| 7 | 修复导入路径 | 所有 `from api.xxx` → `from ocr_api.common.xxx` |
| 8 | 清理 `demo/` | 删除空目录（或保留一个 README 指向新位置） |

---

## 6. 最终结论

| 结论 | 说明 |
|------|------|
| **应该从 demo/ 迁出** | ✅ API 是正式服务，不是 Demo |
| **应该放在 src/ 下** | ✅ 标准 Python 包位置，配合 pyproject.toml |
| **不应该放在核心包内** | ✅ 会污染核心包的依赖 |
| **应该建独立包 `ocr_api`** | ✅ 与 `ocr_three_layer_hybrid` 同级 |
| **应该分 common/ 和 ocr/ 两层** | ✅ 通用基础设施 vs 业务逻辑 |
