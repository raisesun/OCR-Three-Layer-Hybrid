# OCR API 服务接口文档

## 版本: v1.1.0
## 更新日期: 2026-07-08

---

## 一、概述

### 1.1 服务简介

OCR API 服务提供文档识别和字段提取能力，支持图片和PDF文件的异步批量处理。

**核心能力**：
- 文档分类：自动识别文档类型（身份证、户口本、结婚证等）
- 字段提取：从文档中提取结构化字段
- 多格式支持：图片（JPG/PNG/BMP/TIFF）和 PDF
- 异步处理：大批量文件异步提交，支持进度查询和任务取消

**开放接口**（共 5 个）：

| # | 方法 | 路径 | 功能 |
|---|------|------|------|
| 1 | GET | `/health` | 健康检查 |
| 2 | POST | `/api/v1/ocr/async` | 大批量异步提交 |
| 3 | GET | `/api/v1/task/{task_id}` | 查询任务状态 |
| 4 | POST | `/api/v1/task/{task_id}/cancel` | 取消任务 |
| 5 | GET | `/api/v1/quota` | 配额查询 |

### 1.2 服务地址

| 环境 | 地址 | 说明 |
|------|------|------|
| 开发环境 | `http://localhost:8888` | 本地开发 |
| API 文档 | `http://localhost:8888/docs` | Swagger UI（自动生成） |

### 1.3 快速开始

```bash
# 1. 设置 API Key（环境变量）
export OCR_API_KEYS="your_api_key_here"

# 2. 启动服务
python -m ocr_api.ocr.server

# 3. 健康检查
curl http://localhost:8888/health

# 4. 提交异步任务
curl -X POST http://localhost:8888/api/v1/ocr/async \
  -H "Authorization: Bearer $OCR_API_KEYS" \
  -F "files=@test1.jpg" \
  -F "files=@test2.jpg"

# 5. 查询任务状态
curl http://localhost:8888/api/v1/task/{task_id} \
  -H "Authorization: Bearer $OCR_API_KEYS"
```

---

## 二、认证与鉴权

### 2.1 认证方式

使用 **API Key** 进行认证，通过 HTTP Header 传递：

```
Authorization: Bearer {API_KEY}
```

### 2.2 API Key 配置

通过环境变量配置允许的 API Key 列表（逗号分隔）：

```bash
export OCR_API_KEYS="key1,key2,key3"
```

未配置 `OCR_API_KEYS` 时，所有请求将返回 401 错误。

### 2.3 API Key 限制

| 限制项 | 默认值 | 说明 |
|--------|--------|------|
| 速率限制 | 100次/分钟（6000次/小时） | 可通过配额接口查询 |
| 文件大小 | 20MB | 单个文件最大 |
| 异步文件数 | 500个 | 单次异步提交最大文件数 |
| 异步并发 | 100个 | 同时进行的异步任务数 |

---

## 三、接口详情

### 3.1 健康检查

检查服务状态和依赖服务可用性。

```
GET /health
```

**认证**: 不需要

**请求参数**: 无

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 86400.5,
    "checks": {
      "pp_ocr": "ok",
      "vlm_service": "ok",
      "disk_space": "ok"
    }
  },
  "message": "success",
  "request_id": null
}
```

**状态说明**:
| status 值 | 含义 |
|-----------|------|
| `healthy` | 所有依赖正常 |
| `degraded` | 部分依赖异常 |

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 服务可用 |

---

### 3.2 异步任务提交

提交大批量处理任务，立即返回任务ID。后台异步处理，通过查询接口获取进度和结果。

```
POST /api/v1/ocr/async
Content-Type: multipart/form-data
Authorization: Bearer {API_KEY}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | File[] | 是 | 图片/PDF 文件列表，最多 500 个 |
| callback_url | String | 否 | 结果回调 URL（预留，暂未实现） |
| priority | String | 否 | 优先级：`normal`（默认）/ `urgent` |
| enable_vlm | Boolean | 否 | 是否启用 VLM 层，默认 `true` |

**支持的文件格式**: JPG, JPEG, PNG, BMP, PDF, TIFF

**响应示例**:
```json
{
  "code": 202,
  "data": {
    "task_id": "task_20260708_a1b2c3d4e5f6",
    "status": "pending",
    "submitted_at": "2026-07-08T10:30:00",
    "estimated_time": 120,
    "file_count": 10,
    "priority": "normal"
  },
  "message": "任务已提交",
  "request_id": null
}
```

**错误响应**:
```json
{
  "code": 400,
  "data": null,
  "message": "文件数量超限：最多 500 个，当前 600 个",
  "request_id": null
}
```

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 202 | 任务已接受 |
| 400 | 请求参数错误（文件格式不支持、数量超限等） |
| 401 | 认证失败 |
| 413 | 文件过大（>20MB） |

**限制**:
- 文件数量: ≤ 500 个
- 单文件大小: ≤ 20MB
- 同时进行的任务: ≤ 100 个

---

### 3.3 查询任务状态

查询异步任务的处理状态、进度和结果。

```
GET /api/v1/task/{task_id}
Authorization: Bearer {API_KEY}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | String | 任务 ID |

**响应示例 — 处理中**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260708_a1b2c3d4e5f6",
    "status": "processing",
    "progress": 60,
    "processed": 6,
    "total": 10,
    "submitted_at": "2026-07-08T10:30:00",
    "started_at": "2026-07-08T10:30:05",
    "completed_at": null,
    "estimated_remaining": 48,
    "result": null,
    "error": null
  },
  "message": "success",
  "request_id": null
}
```

**响应示例 — 已完成**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260708_a1b2c3d4e5f6",
    "status": "completed",
    "progress": 100,
    "processed": 10,
    "total": 10,
    "submitted_at": "2026-07-08T10:30:00",
    "started_at": "2026-07-08T10:30:05",
    "completed_at": "2026-07-08T10:32:05",
    "estimated_remaining": null,
    "result": {
      "results": [
        {
          "file_name": "id_card.jpg",
          "status": "success",
          "classification": {
            "doc_type": "身份证",
            "doc_type_label": "身份证",
            "confidence": 0.95,
            "route": "standard_certificate",
            "signal": "公民身份号码"
          },
          "extraction": {
            "success": true,
            "layer": "rule",
            "fields": {
              "姓名": "张三",
              "公民身份号码": "110101199001011234"
            }
          },
          "timing": {
            "classify_ms": 2.5,
            "extract_ms": 150.3,
            "total_ms": 152.8
          }
        }
      ],
      "summary": {
        "total": 10,
        "success": 9,
        "failed": 1,
        "total_time_ms": 120500,
        "avg_time_ms": 12050.0
      }
    },
    "error": null
  },
  "message": "success",
  "request_id": null
}
```

**响应示例 — 任务不存在**:
```json
{
  "code": 404,
  "data": null,
  "message": "任务不存在: task_invalid_id",
  "request_id": null
}
```

**任务状态说明**:
| 状态 | 说明 | 可取消 |
|------|------|--------|
| `pending` | 等待处理 | ✅ |
| `processing` | 处理中（progress 表示进度百分比） | ✅ |
| `completed` | 已完成（result 包含完整结果） | ❌ |
| `failed` | 失败（error 包含错误信息） | ❌ |
| `cancelled` | 已取消 | ❌ |

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 401 | 认证失败 |
| 404 | 任务不存在 |

---

### 3.4 取消任务

取消正在处理的异步任务。

```
POST /api/v1/task/{task_id}/cancel
Authorization: Bearer {API_KEY}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | String | 任务 ID |

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260708_a1b2c3d4e5f6",
    "status": "cancelled",
    "processed": 5,
    "total": 10
  },
  "message": "任务已取消",
  "request_id": null
}
```

**错误响应**:
```json
{
  "code": 400,
  "data": null,
  "message": "任务状态为 completed，无法取消（仅 pending/processing 可取消）",
  "request_id": null
}
```

**限制**:
- 仅可取消 `pending` 或 `processing` 状态的任务
- 取消是异步的，可能不会立即停止当前正在处理的文件
- 已完成的文件结果会被保留但不返回

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 取消成功 |
| 400 | 任务状态不允许取消 |
| 401 | 认证失败 |
| 404 | 任务不存在 |

---

### 3.5 配额查询

查询 API 调用配额使用情况。

```
GET /api/v1/quota
Authorization: Bearer {API_KEY}
```

**请求参数**: 无

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "api_calls": {
      "used": 450,
      "limit": 6000,
      "reset_at": "2026-07-08T11:00:00"
    },
    "storage": {
      "used_mb": 1024.5,
      "limit_mb": 10240
    },
    "async_tasks": {
      "pending": 5,
      "limit": 100
    }
  },
  "message": "success",
  "request_id": null
}
```

**字段说明**:
| 字段 | 说明 |
|------|------|
| `api_calls.used` | 当前小时已调用次数 |
| `api_calls.limit` | 每小时上限（默认 6000） |
| `api_calls.reset_at` | 配额重置时间 |
| `storage.used_mb` | 已用存储空间 (MB) |
| `storage.limit_mb` | 存储上限 (MB)（默认 10240 = 10GB） |
| `async_tasks.pending` | 当前排队/处理中的任务数 |
| `async_tasks.limit` | 并发上限（默认 100） |

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 401 | 认证失败 |

---

## 四、数据模型

### 4.1 文档类型

| 类型代码 | 中文名称 | 说明 |
|----------|----------|------|
| `身份证` | 身份证 | 自动识别正反面 |
| `户口本` | 户口本 | 自动识别首页/个人页 |
| `结婚证` | 结婚证 | |
| `离婚证` | 离婚证 | |
| `不动产权证书` | 不动产权证书 | |
| `发票` | 发票 | |
| `购房合同` | 购房合同 | 多页文档 |
| `存量房合同` | 存量房合同 | 多页文档 |
| `资金监管协议` | 资金监管协议 | |
| `驾驶证` | 驾驶证 | |
| `行驶证` | 行驶证 | |
| `银行卡` | 银行卡 | |
| `空运提单` | 空运提单 | |
| `快递单` | 快递单 | |
| `未知` | 未知 | 无法识别的文档 |

### 4.2 处理层

| 层代码 | 说明 | 平均耗时 |
|--------|------|----------|
| `rule` | 规则层（正则表达式 + 位置感知） | 10-50ms |
| `vlm` | VLM层（多模态大模型兜底） | 30-120s |

### 4.3 统一响应格式

所有接口返回统一的 JSON 格式：

**成功响应**:
```json
{
  "code": 200,
  "data": { ... },
  "message": "success",
  "request_id": null
}
```

**错误响应**:
```json
{
  "code": 400,
  "data": null,
  "message": "错误描述",
  "request_id": null
}
```

---

## 五、错误处理

### 5.1 错误码

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | - |
| 202 | 任务已接受 | 使用 task_id 查询结果 |
| 400 | 请求参数错误 | 检查请求参数 |
| 401 | 认证失败 | 检查 API Key |
| 404 | 资源不存在 | 检查 task_id |
| 413 | 文件过大 | 压缩文件或减小单文件大小 |
| 500 | 服务器内部错误 | 联系技术支持 |

---

## 六、使用示例

### 6.1 Python 示例

```python
import requests
import time

API_BASE = "http://localhost:8888"
API_KEY = "your_api_key_here"
headers = {"Authorization": f"Bearer {API_KEY}"}

# 1. 健康检查
resp = requests.get(f"{API_BASE}/health")
print(resp.json())

# 2. 提交异步任务
files = []
for f in ["doc1.jpg", "doc2.jpg", "doc3.pdf"]:
    files.append(("files", open(f, "rb")))

resp = requests.post(
    f"{API_BASE}/api/v1/ocr/async",
    headers=headers,
    files=files,
)
task_id = resp.json()["data"]["task_id"]
print(f"任务已提交: {task_id}")

# 3. 轮询任务状态
while True:
    resp = requests.get(
        f"{API_BASE}/api/v1/task/{task_id}",
        headers=headers,
    )
    data = resp.json()["data"]
    status = data["status"]
    progress = data["progress"]
    print(f"进度: {progress}% ({data['processed']}/{data['total']})")

    if status == "completed":
        results = data["result"]["results"]
        summary = data["result"]["summary"]
        print(f"完成! 成功={summary['success']}, 失败={summary['failed']}")
        break
    elif status == "failed":
        print(f"失败: {data.get('error')}")
        break

    time.sleep(5)  # 每 5 秒查询一次

# 4. 查询配额
resp = requests.get(f"{API_BASE}/api/v1/quota", headers=headers)
quota = resp.json()["data"]
print(f"API 调用: {quota['api_calls']['used']}/{quota['api_calls']['limit']}")
```

### 6.2 cURL 示例

```bash
# 健康检查
curl http://localhost:8888/health

# 提交异步任务
curl -X POST http://localhost:8888/api/v1/ocr/async \
  -H "Authorization: Bearer $API_KEY" \
  -F "files=@doc1.jpg" \
  -F "files=@doc2.jpg" \
  -F "files=@doc3.pdf"

# 查询任务状态
curl http://localhost:8888/api/v1/task/task_20260708_a1b2c3d4e5f6 \
  -H "Authorization: Bearer $API_KEY"

# 取消任务
curl -X POST http://localhost:8888/api/v1/task/task_20260708_a1b2c3d4e5f6/cancel \
  -H "Authorization: Bearer $API_KEY"

# 查询配额
curl http://localhost:8888/api/v1/quota \
  -H "Authorization: Bearer $API_KEY"
```

---

## 七、限制与配额

### 7.1 默认限制

| 限制项 | 默认值 | 说明 |
|--------|--------|------|
| API 调用频率 | 6000次/小时（100次/分钟） | 按小时重置 |
| 单文件大小 | 20MB | 单个文件最大 |
| 异步提交文件数 | 500 个 | 单次提交最多 |
| 异步并发任务 | 100 个 | 同时处理的任务上限 |
| 存储配额 | 10GB | 上传文件总空间 |

### 7.2 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OCR_API_KEYS` | API Key 列表（逗号分隔） | 空（必须配置） |
| `DEBUG` | 启用调试路由 | `false` |
| `OCR_DB_PATH` | SQLite 数据库路径 | `/tmp/ocr_tasks.db` |
| `OCR_PORT` | 服务端口 | `8888` |

---

## 八、最佳实践

### 8.1 处理模式选择

- **1-10 张**: 使用异步 API，简单高效
- **10-500 张**: 使用异步 API，一次提交
- **>500 张**: 分批提交多个异步任务

### 8.2 轮询策略

- 查询间隔建议 5-10 秒
- 根据 `estimated_remaining` 字段动态调整间隔
- 大文件多的任务可适当增大间隔

### 8.3 错误处理

- 401 错误：检查 API Key 是否正确
- 413 错误：压缩文件或分批提交
- 500 错误：指数退避重试（1s, 2s, 4s, 8s...）

### 8.4 安全建议

- 不要在前端代码中暴露 API Key
- 使用环境变量或密钥管理服务存储
- 生产环境建议配置 HTTPS（通过反向代理）

---

## 九、更新日志

### v1.1.0 (2026-07-08)
- 限制开放接口为 5 个（移除同步单张/批量处理）
- 新增 SQLite 持久化任务管理
- 新增 API Key 认证
- 新增配额查询接口
- 调试功能降级为环境变量控制（DEBUG=true）

### v1.0.0 (2026-07-05)
- 初始版本（设计文档）

---

## 十、调试模式

设置 `DEBUG=true` 可启用额外的调试路由，用于本地开发和测试：

```bash
DEBUG=true python -m ocr_api.ocr.server
```

调试路由包括：
- `GET /` — Demo UI 主页
- `POST /api/process` — 单图处理（传路径）
- `POST /api/process/batch` — 按 Case 批量处理
- `POST /api/process/batch/directory` — 目录批量处理
- `GET /api/directories` — 目录浏览
- `GET /api/baseline/cases` — 基线数据列表
- `POST /api/baseline/compare` — 基线对比
- `GET /api/stats/dashboard` — 统计面板
- `POST /api/upload` — 文件上传

**注意**: 调试路由不应暴露给外部用户。
