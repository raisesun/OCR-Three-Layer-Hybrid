# OCR API 服务接口文档

## 版本: v1.0.0
## 更新日期: 2026-07-05

---

## 一、概述

### 1.1 服务简介

OCR API 服务提供文档识别和字段提取能力，支持图片和PDF文件的处理。

**核心能力**：
- 文档分类：自动识别文档类型（身份证、户口本、结婚证等）
- 字段提取：从文档中提取结构化字段
- 多格式支持：图片（JPG/PNG/BMP）和PDF（扫描件+文字版）
- 双模式处理：同步（实时）和异步（大批量）

### 1.2 服务地址

| 环境 | 地址 | 说明 |
|------|------|------|
| 开发环境 | `http://localhost:8000` | 本地开发 |
| 测试环境 | `http://ocr-test.internal:8080` | 局域网测试 |
| 生产环境 | `https://ocr.api.example.com` | 公网生产 |

### 1.3 快速开始

```bash
# 1. 获取API Key
# 联系管理员获取

# 2. 测试健康检查
curl http://localhost:8000/health

# 3. 处理单张图片
curl -X POST http://localhost:8000/api/v1/ocr/single \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@test.jpg"

# 4. 查看API文档
# 浏览器访问: http://localhost:8000/docs
```

---

## 二、认证与鉴权

### 2.1 认证方式

使用 **API Key** 进行认证，通过 HTTP Header 传递：

```
Authorization: Bearer {API_KEY}
```

### 2.2 API Key 管理

#### 获取API Key
联系系统管理员申请，提供以下信息：
- 应用名称
- 使用场景说明
- 预期调用量

#### API Key 权限

| 权限 | 说明 |
|------|------|
| `ocr.read` | 调用OCR识别接口 |
| `ocr.write` | 上传文件（通常与read一起授予） |
| `task.read` | 查询任务状态 |
| `admin` | 管理权限（查看用量、重置Key等） |

#### API Key 限制

| 限制项 | 默认值 | 说明 |
|--------|--------|------|
| 速率限制 | 100次/分钟 | 可根据需求调整 |
| 文件大小 | 20MB | 单个文件最大 |
| 批量数量 | 50个 | 单次批量处理最大文件数 |
| 异步队列 | 100个 | 同时进行的异步任务数 |

---

## 三、接口列表

### 3.1 健康检查

检查服务状态和依赖服务可用性。

```
GET /health
```

**请求参数**: 无

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 86400,
    "checks": {
      "database": "ok",
      "pp_ocr": "ok",
      "vlm_service": "ok",
      "disk_space": "ok"
    }
  },
  "message": "success"
}
```

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 服务正常 |
| 503 | 服务不可用 |

---

### 3.2 同步单张处理

处理单张图片/PDF，实时返回结果。

```
POST /api/v1/ocr/single
Content-Type: multipart/form-data
Authorization: Bearer {API_KEY}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | 图片/PDF文件，支持JPG/PNG/BMP/PDF |
| doc_type | String | 否 | 指定文档类型，不传则自动分类 |
| enable_vlm | Boolean | 否 | 是否启用VLM层，默认true |

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "classification": {
      "doc_type": "身份证-正面",
      "confidence": 0.95,
      "route": "standard_certificate",
      "signal": "公民身份号码"
    },
    "extraction": {
      "success": true,
      "layer": "rule",
      "fields": {
        "姓名": "张三",
        "性别": "男",
        "民族": "汉",
        "出生": "1990年1月1日",
        "住址": "北京市XX区XX路XX号",
        "公民身份号码": "110101199001011234"
      },
      "vlm_fallback_enabled": true,
      "vlm_fallback_triggered": false,
      "vlm_fallback_fields": []
    },
    "timing": {
      "classify_ms": 2.5,
      "extract_ms": 150.3,
      "total_ms": 152.8
    },
    "image_info": {
      "filename": "test.jpg",
      "size_bytes": 1024000,
      "format": "JPEG",
      "dimensions": "1920x1080"
    }
  },
  "message": "success"
}
```

**错误响应**:
```json
{
  "code": 400,
  "data": null,
  "message": "文件格式不支持，仅支持JPG/PNG/BMP/PDF"
}
```

**状态码**:
| 状态码 | 说明 |
|--------|------|
| 200 | 处理成功 |
| 400 | 请求参数错误 |
| 401 | 认证失败 |
| 413 | 文件过大 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |
| 503 | VLM服务不可用（已降级） |

**限制**:
- 文件大小: ≤20MB
- 处理时间: 规则层<10秒，VLM层<180秒
- 超时设置: 建议客户端设置180秒超时

---

### 3.3 同步批量处理

处理多张图片/PDF，实时返回所有结果。

```
POST /api/v1/ocr/batch
Content-Type: multipart/form-data
Authorization: Bearer {API_KEY}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | File[] | 是 | 多个图片/PDF文件，最多50个 |
| doc_type | String | 否 | 指定文档类型，所有文件统一分类 |
| enable_vlm | Boolean | 否 | 是否启用VLM层，默认true |

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "results": [
      {
        "filename": "id_card.jpg",
        "status": "success",
        "classification": { ... },
        "extraction": { ... },
        "timing": { ... }
      },
      {
        "filename": "hukou.pdf",
        "status": "success",
        "classification": { ... },
        "extraction": { ... },
        "timing": { ... }
      }
    ],
    "summary": {
      "total": 2,
      "success": 2,
      "failed": 0,
      "total_time_ms": 350.5,
      "avg_time_ms": 175.25
    }
  },
  "message": "success"
}
```

**限制**:
- 文件数量: ≤50个
- 总大小: ≤100MB
- 处理时间: 可能较长，建议设置300秒超时

---

### 3.4 异步任务提交

提交大批量处理任务，立即返回任务ID。

```
POST /api/v1/ocr/async
Content-Type: multipart/form-data
Authorization: Bearer {API_KEY}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | File[] | 是 | 多个图片/PDF文件 |
| callback_url | String | 否 | 结果回调URL，处理完成后POST通知 |
| priority | String | 否 | 优先级：normal（默认）/ urgent |
| enable_vlm | Boolean | 否 | 是否启用VLM层，默认true |

**响应示例**:
```json
{
  "code": 202,
  "data": {
    "task_id": "task_20260705_abc123",
    "status": "pending",
    "submitted_at": "2026-07-05T10:30:00Z",
    "estimated_time": 120,
    "file_count": 10,
    "priority": "normal"
  },
  "message": "任务已提交"
}
```

**限制**:
- 文件数量: ≤500个
- 总大小: ≤500MB
- 队列长度: 最多100个待处理任务

---

### 3.5 查询任务状态

查询异步任务的处理状态和结果。

```
GET /api/v1/task/{task_id}
Authorization: Bearer {API_KEY}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | String | 任务ID |

**响应示例 - 处理中**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260705_abc123",
    "status": "processing",
    "progress": 60,
    "processed": 6,
    "total": 10,
    "submitted_at": "2026-07-05T10:30:00Z",
    "started_at": "2026-07-05T10:30:05Z",
    "estimated_remaining": 48
  },
  "message": "success"
}
```

**响应示例 - 已完成**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260705_abc123",
    "status": "completed",
    "progress": 100,
    "processed": 10,
    "total": 10,
    "submitted_at": "2026-07-05T10:30:00Z",
    "started_at": "2026-07-05T10:30:05Z",
    "completed_at": "2026-07-05T10:32:05Z",
    "result": {
      "results": [ ... ],
      "summary": { ... }
    }
  },
  "message": "success"
}
```

**响应示例 - 失败**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260705_abc123",
    "status": "failed",
    "progress": 30,
    "processed": 3,
    "total": 10,
    "error": "VLM服务超时，已处理3张后失败",
    "partial_result": {
      "results": [ ... ]
    }
  },
  "message": "任务失败"
}
```

**任务状态**:
| 状态 | 说明 |
|------|------|
| pending | 等待处理 |
| processing | 处理中 |
| completed | 已完成 |
| failed | 失败 |
| cancelled | 已取消 |

---

### 3.6 取消任务

取消正在处理的异步任务。

```
POST /api/v1/task/{task_id}/cancel
Authorization: Bearer {API_KEY}
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260705_abc123",
    "status": "cancelled",
    "processed": 5,
    "total": 10
  },
  "message": "任务已取消"
}
```

**限制**:
- 仅可取消 pending 或 processing 状态的任务
- 已处理的部分结果不会返回

---

## 四、数据模型

### 4.1 文档类型

| 类型代码 | 中文名称 | 说明 |
|----------|----------|------|
| `id_card` | 身份证 | 自动识别正反面 |
| `id_card_front` | 身份证-正面 | |
| `id_card_back` | 身份证-背面 | |
| `household_register` | 户口本 | 自动识别首页/个人页 |
| `household_register_cover` | 户口本-首页 | |
| `household_register_content` | 户口本-个人页 | |
| `marriage_certificate` | 结婚证 | 自动识别封面/内容页/盖章页 |
| `divorce_certificate` | 离婚证 | 自动识别封面/内容页/盖章页 |
| `property_certificate` | 不动产权证书 | 自动识别首页/内容页/附图页 |
| `invoice` | 发票 | |
| `purchase_contract` | 购房合同 | 自动识别首页/内容页/签署页 |
| `stock_contract` | 存量房合同 | 自动识别首页/内容页/签署页 |
| `fund_supervision` | 资金监管协议 | 自动识别首页/信息页/签章页 |
| `fund_supervision_certificate` | 资金监管凭证 | |
| `driver_license` | 驾驶证 | 自动识别正反面 |
| `vehicle_license` | 行驶证 | 自动识别正反面 |
| `bank_card` | 银行卡 | 自动识别正反面 |
| `air_waybill` | 空运提单 | |
| `express_waybill` | 快递单 | |
| `unknown` | 未知 | 无法识别的文档 |

### 4.2 处理层

| 层代码 | 说明 | 平均耗时 |
|--------|------|----------|
| `rule` | 规则层（正则表达式） | 10-50ms |
| `vlm` | VLM层（多模态大模型） | 30-120s |

### 4.3 分类路由

| 路由代码 | 说明 |
|----------|------|
| `standard_certificate` | 标准证件强信号匹配 |
| `backup_certificate` | 备选强信号匹配 |
| `additional_backup` | 更多备选信号匹配 |
| `standard_document` | 标准单证强信号匹配 |
| `contract_field_combination` | 合同字段组合匹配 |
| `vlm_fallback_required` | VLM兜底（无法识别） |

---

## 五、错误处理

### 5.1 错误码

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | - |
| 202 | 任务已接受 | 使用task_id查询结果 |
| 400 | 请求参数错误 | 检查请求参数 |
| 401 | 认证失败 | 检查API Key |
| 403 | 权限不足 | 联系管理员提升权限 |
| 413 | 文件过大 | 压缩文件或分批处理 |
| 429 | 请求频率超限 | 降低请求频率 |
| 500 | 服务器内部错误 | 联系技术支持 |
| 503 | 服务不可用 | 稍后重试 |

### 5.2 错误响应格式

```json
{
  "code": 400,
  "data": null,
  "message": "错误描述",
  "details": {
    "field": "file",
    "issue": "文件格式不支持"
  },
  "request_id": "req_abc123"
}
```

---

## 六、使用示例

### 6.1 Python示例

```python
import requests
import json

# 配置
API_BASE = "http://localhost:8000"
API_KEY = "your_api_key_here"
headers = {"Authorization": f"Bearer {API_KEY}"}

# 1. 健康检查
response = requests.get(f"{API_BASE}/health")
print(response.json())

# 2. 同步单张处理
with open("test.jpg", "rb") as f:
    response = requests.post(
        f"{API_BASE}/api/v1/ocr/single",
        headers=headers,
        files={"file": ("test.jpg", f, "image/jpeg")}
    )
    result = response.json()
    print(f"文档类型: {result['data']['classification']['doc_type']}")
    print(f"提取字段: {result['data']['extraction']['fields']}")

# 3. 异步批量处理
files = []
for i in range(10):
    files.append(("files", open(f"page_{i}.jpg", "rb")))

response = requests.post(
    f"{API_BASE}/api/v1/ocr/async",
    headers=headers,
    files=files,
    data={"callback_url": "https://your-app.com/callback"}
)
task_id = response.json()["data"]["task_id"]
print(f"任务ID: {task_id}")

# 4. 查询任务状态
response = requests.get(
    f"{API_BASE}/api/v1/task/{task_id}",
    headers=headers
)
print(response.json())
```

### 6.2 cURL示例

```bash
# 同步单张处理
curl -X POST http://localhost:8000/api/v1/ocr/single \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@test.jpg" \
  -F "enable_vlm=true"

# 同步批量处理
curl -X POST http://localhost:8000/api/v1/ocr/batch \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "files=@file1.jpg" \
  -F "files=@file2.jpg" \
  -F "files=@file3.jpg"

# 异步任务提交
curl -X POST http://localhost:8000/api/v1/ocr/async \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "files=@batch/*.jpg" \
  -F "callback_url=https://your-app.com/callback"

# 查询任务状态
curl -X GET http://localhost:8000/api/v1/task/task_abc123 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## 七、限制与配额

### 7.1 默认限制

| 限制项 | 默认值 | 可申请调整 |
|--------|--------|------------|
| API调用频率 | 100次/分钟 | 是 |
| 单文件大小 | 20MB | 是 |
| 批量文件数 | 50个 | 是 |
| 异步队列长度 | 100个 | 是 |
| 总存储配额 | 10GB | 是 |

### 7.2 配额查询

```
GET /api/v1/quota
Authorization: Bearer {API_KEY}
```

**响应示例**:
```json
{
  "code": 200,
  "data": {
    "api_calls": {
      "used": 450,
      "limit": 6000,
      "reset_at": "2026-07-05T11:00:00Z"
    },
    "storage": {
      "used_mb": 1024,
      "limit_mb": 10240
    },
    "async_tasks": {
      "pending": 5,
      "limit": 100
    }
  },
  "message": "success"
}
```

---

## 八、最佳实践

### 8.1 性能优化

1. **选择合适的处理模式**
   - 1-10张：使用同步API
   - 10-100张：使用异步API
   - >100张：分批提交异步任务

2. **指定文档类型**
   - 如果已知文档类型，传入`doc_type`参数可跳过分类步骤
   - 节省1-5ms分类时间

3. **控制VLM使用**
   - 简单文档（身份证、发票）可禁用VLM：`enable_vlm=false`
   - 复杂文档（合同、户口本）建议启用VLM

### 8.2 错误处理

1. **重试策略**
   - 500/503错误：指数退避重试
   - 429错误：等待限流重置
   - 400/401错误：不重试，修复请求

2. **超时设置**
   - 同步单张：180秒
   - 同步批量：300秒
   - 异步查询：30秒

### 8.3 安全建议

1. **API Key保护**
   - 不要在前端代码中暴露API Key
   - 使用环境变量或密钥管理服务存储
   - 定期轮换API Key

2. **HTTPS**
   - 生产环境必须使用HTTPS
   - 不要通过HTTP传输API Key

---

## 九、更新日志

### v1.0.0 (2026-07-05)
- 初始版本发布
- 支持同步单张/批量处理
- 支持异步任务处理
- 支持图片和PDF文件
- API Key认证

---

## 十、相关文档

- [代码执行流程图](代码执行流程图.md) — 了解OCR处理流程
- [扩展指南：新增证件类型](扩展指南_新增证件类型.md) — 了解如何扩展支持新文档类型
- [技术方案分析](../analysis/analysis_20260705_OCR_API服务技术方案.md) — 详细的技术方案分析
