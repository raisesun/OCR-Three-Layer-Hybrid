# OCR 两层混合架构 — 文档识别与字段提取服务

基于规则 + VLM 的两层混合提取架构，配合关键词分类器与字段级 VLM 重试，支持身份证、户口本、房产证、购房合同、发票、离婚协议等多类文档的自动识别与结构化提取。

## 架构概览

```
输入：文档图片
  │
  ▼
OCR 文本提取 (PaddleOCR PP-OCRv6)
  │
  ▼
Layer 1: 文档分类 (classifier.py)
  6 级联关键词路由 → 输出 DocumentInfo
  │
  ├── 已知文档类型 ──────────────────────────────────────┐
  │                                                       │
  ▼                                                       ▼
Layer 2A: 规则层 (rule_layer.py)              Layer 2B: VLM 层 (vlm_layer.py)
  正则提取 → 4 个领域提取器                      视觉模型提取 (Qwen2.5-VL-7B)
  + 位置标注 (PaddleOCR 坐标)                    结构化 Prompt → JSON 解析
  │                                                       │
  └────────────────────────┬──────────────────────────────┘
                           │
                           ▼
Layer 3: VLM 字段级兜底 (vlm_fallback.py)
  校验失败字段 → VLM 重新提取 → 合并结果
  │
  ▼
输出：ExtractionResult { doc_type, fields, success }
```

## 项目结构

```
OCR-Three-Layer-Hybrid/
│
├── src/
│   ├── ocr_api/                          ── API 服务层 (FastAPI) ──
│   │   ├── common/                       可复用基础设施
│   │   │   ├── auth.py                   API Key 认证 (Bearer Token)
│   │   │   ├── schemas.py                Pydantic 请求/响应模型
│   │   │   └── task_manager.py           SQLite 异步任务队列 + 租户配额
│   │   │
│   │   └── ocr/                          OCR 业务路由
│   │       ├── server.py                 主入口：create_app() 工厂 + uvicorn
│   │       ├── routes/
│   │       │   ├── health.py             GET  /health
│   │       │   ├── ocr.py                POST /api/v1/ocr/async (文件上传)
│   │       │   ├── task.py               GET  /api/v1/task/{id} (查询/取消)
│   │       │   └── quota.py              GET  /api/v1/quota (租户配额)
│   │       ├── baseline_service.py       基线对比服务 (DEBUG 模式)
│   │       └── debug_routes.py           Demo UI + 调试路由 (DEBUG 模式)
│   │
│   └── ocr_three_layer_hybrid/           ── 核心领域层 ──
│       │
│       │  ★ 接口与配置
│       ├── interfaces.py                 核心类型：DocumentType, ExtractionResult, ABC
│       ├── config.py                     统一配置：OCRConfig, VLMServiceConfig
│       ├── field_config.py               文档类型 → 字段优先级 (required/optional/skip)
│       │
│       │  ★ 服务入口
│       ├── service.py                    OCRService：公开 API (single/multi/batch)
│       ├── pipeline.py                   PlanEPlusPipeline：编排器 (分类→提取→兜底)
│       │
│       │  ★ 处理层
│       ├── classifier.py                 Layer 1：6 级联关键词文档分类
│       ├── rule_layer.py                 Layer 2A：正则提取 (分发到 4 个提取器)
│       ├── vlm_layer.py                  Layer 2B：VLM 视觉模型提取
│       ├── vlm_fallback.py               Layer 3：VLM 字段级兜底
│       ├── position_extractor.py         空间位置提取 (PaddleOCR 坐标)
│       │
│       │  ★ 提取器
│       ├── extractors/
│       │   ├── base_extractor.py         抽象基类
│       │   ├── personal_id_extractor.py  身份证 / 结婚证 / 离婚证
│       │   ├── household_property_extractor.py  户口本 / 房产证
│       │   ├── financial_extractor.py    发票 / 合同 / 资金监管
│       │   ├── agreement_extractor.py    离婚协议
│       │   └── regex_patterns.py         共享正则模式
│       │
│       │  ★ 基础设施
│       ├── external_services.py          VLMClient (HTTP 重试 + base64 编码)
│       ├── paddleocr_wrapper.py          PaddleOCR 引擎封装
│       ├── prompt_templates.py           VLM Prompt 模板 (按文档类型)
│       ├── field_validator.py            字段校验器 (正则/长度/字符类型)
│       ├── json_utils.py                 JSON 解析 + 字段合并工具
│       ├── text_preprocessor.py          OCR 文本预处理
│       ├── image_preprocessor.py         图像增强 (去噪/纠偏/对比度)
│       └── ui_metadata.py               前端流程图常量
│
├── tests/
│   ├── unit/                             单元测试
│   ├── integration/                      集成测试
│   └── fixtures/                         测试数据
│
├── scripts/                              运维脚本
├── analysis/                             分析文档
└── docs/                                 设计文档
```

## 快速启动

### 1. 启动外部服务

```bash
# PaddleOCR PP-OCRv6 — 本地进程，无需额外启动

# Qwen2.5-VL-7B (VLM 提取/兜底)
llama-server -m qwen2.5-vl-7b-q4_k_m.gguf --mmproj mmproj-qwen2.5-vl-7b.gguf \
  --port 8082 --chat-template qwen2-vl

# GLM-OCR (备选 VLM)
llama-server -m glm-ocr-q8_0.gguf --mmproj mmproj-glm-ocr.gguf \
  --port 8080 --chat-template glm
```

### 2. 启动 API 服务

```bash
# 从 src/ 目录启动
cd src
python -m ocr_api.ocr.server

# 或直接指定 PYTHONPATH
PYTHONPATH=src python -m ocr_api.ocr.server
```

服务默认监听端口 **8888**，API 文档访问 http://localhost:8888/docs

### 3. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OCR_API_KEYS` | (无) | API Key 列表，逗号分隔（如 `key1,key2`） |
| `OCR_PORT` | `8888` | 服务端口 |
| `OCR_DB_PATH` | `/tmp/ocr_tasks.db` | SQLite 任务数据库路径 |
| `GLM_OCR_URL` | `http://localhost:8080/v1` | GLM-OCR 服务地址 |
| `QWEN_VLM_URL` | `http://localhost:8082/v1` | Qwen2.5-VL 服务地址 |
| `DEBUG` | `false` | 设为 `true` 启用调试路由（Demo UI、基线对比） |

### 4. 调用示例

```bash
# 提交异步批量任务（最多 500 文件）
curl -X POST http://localhost:8888/api/v1/ocr/async \
  -H "Authorization: Bearer <your_api_key>" \
  -F "files=@document1.jpg" \
  -F "files=@document2.png"

# 返回：{"task_id": "task_20260709_abc123...", "status": "pending"}

# 查询任务进度
curl http://localhost:8888/api/v1/task/task_20260709_abc123 \
  -H "Authorization: Bearer <your_api_key>"

# 取消任务
curl -X POST http://localhost:8888/api/v1/task/task_20260709_abc123/cancel \
  -H "Authorization: Bearer <your_api_key>"

# 健康检查（无需认证）
curl http://localhost:8888/health

# 查询租户配额
curl http://localhost:8888/api/v1/quota \
  -H "Authorization: Bearer <your_api_key>"
```

## 技术特性

| 特性 | 实现 |
|------|------|
| API 框架 | FastAPI + uvicorn，`create_app()` 工厂模式 |
| 认证 | Bearer Token，模块级单例 `APIKeyAuthenticator` |
| 异步任务 | `asyncio.Task` + SQLite 持久化，WAL 模式 |
| 线程安全 | thread-local SQLite 连接 + 乐观锁 |
| 租户隔离 | `tasks.api_key` 关联，配额 JOIN 查询 |
| 文档分类 | 6 级联关键词路由，置信度 0.60-0.95 |
| 规则提取 | 4 个领域提取器 + PaddleOCR 坐标位置标注 |
| VLM 提取 | OpenAI 兼容 API，base64 图片，指数退避重试 |
| JSON 解析 | 3 层 fallback（直接解析 / 去 markdown / 括号匹配） |
| 字段校验 | 正则 + 长度 + 字符类型 + 地址关键词 |
| 兜底策略 | 校验失败字段调用 VLM 重新提取，仅覆盖空字段 |
| 批量处理 | 最多 500 文件，逐文件处理，支持取消 |

## 外部服务

| 服务 | 端口 | 用途 |
|------|------|------|
| PaddleOCR PP-OCRv6 | 本地 | OCR 文本提取 + 坐标信息 |
| Qwen2.5-VL-7B | 8082 | 默认 VLM 引擎（提取 + 兜底） |
| GLM-OCR | 8080 | 备选 VLM 引擎 |

## 测试

```bash
# 单元测试
PYTHONPATH=src python3 -m pytest tests/unit/ -v

# 集成测试（需要启动外部服务）
PYTHONPATH=src python3 -m pytest \
  tests/integration/test_health.py \
  tests/integration/test_auth.py \
  tests/integration/test_ocr_async.py \
  tests/integration/test_task.py \
  tests/integration/test_quota.py \
  -v
```
