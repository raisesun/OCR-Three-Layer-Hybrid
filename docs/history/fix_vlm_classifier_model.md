# VLM 分类器模型修复说明

## 问题描述

**发现时间**：2026-07-01  
**严重程度**：🔴 严重（VLM 分类兜底功能失效）

### 问题详情

VLM 分类器错误地使用了 **Qwen3.5-4B**（纯文本模型）进行文档分类，但该任务需要**多模态视觉语言模型**来处理图片。

**错误配置**：
- 模型：`Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf`
- 端口：8081
- 问题：Qwen3.5-4B 是纯文本 LLM，无法处理图片

**代码表现**：
```python
# external_services.py - ClassificationClient.classify()
payload = {
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {...}},  # ← 发送图片
            ],
        }
    ],
}
# 但 Qwen3.5-4B 无法接收图片！
```

**影响**：
- VLM 分类兜底功能完全失效
- 当规则分类器无法判定文档类型时，无法通过 VLM 进行兜底分类
- 可能导致更多文档被标记为 UNKNOWN，影响后续提取流程

---

## 修复方案

### 核心思路

使用已有的 **Qwen2.5-VL-7B**（端口 8082）替代 Qwen3.5-4B（端口 8081）进行 VLM 分类。

**模型对比**：

| 模型 | 类型 | 能否处理图片 | 端口 | 用途 |
|------|------|------------|------|------|
| Qwen3.5-4B | 文本 LLM | ❌ 否 | 8081 | ~~VLM 分类~~（错误） |
| Qwen2.5-VL-7B | 视觉语言模型 | ✅ 是 | 8082 | VLM 分类 + 字段提取 |
| GLM-OCR | 视觉语言模型 | ✅ 是 | 8080 | VLM 字段提取 + OCR |

### 修改内容

#### 1. 配置文件 (`config.py`)

```python
# 修改前
@dataclass
class ClassificationServiceConfig:
    """Qwen VLM 分类服务配置（端口8081）"""
    base_url: str = "http://localhost:8081/v1"
    model_name: str = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
    timeout: float = 120.0

# 修改后
@dataclass
class ClassificationServiceConfig:
    """Qwen2.5-VL-7B 视觉模型服务配置（端口8082）
    
    用于：
    - VLM分类器 (vlm_classifier.py) — 文档分类兜底
    注意：必须是多模态模型（视觉语言模型），不能用纯文本模型
    """
    base_url: str = "http://localhost:8082/v1"
    model_name: str = "qwen2.5-vl-7b"
    timeout: float = 120.0
```

#### 2. VLM 分类器 (`vlm_classifier.py`)

```python
# 修改前
DEFAULT_BASE_URL = "http://localhost:8081/v1"
DEFAULT_MODEL = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"

# 修改后
# 注意：必须使用多模态模型（视觉语言模型），不能用纯文本模型
DEFAULT_BASE_URL = "http://localhost:8082/v1"
DEFAULT_MODEL = "qwen2.5-vl-7b"
```

#### 3. 外部服务客户端 (`external_services.py`)

```python
# 修改前
"""
- ClassificationClient: Qwen VLM 分类模型（端口8081），用于文档分类
"""

class ClassificationClient:
    """Qwen VLM 分类客户端
    封装对 llama-server (Qwen3.5-4B) 的 OpenAI 兼容 API 调用。
    """

# 修改后
"""
- ClassificationClient: Qwen2.5-VL-7B 视觉模型（端口8082），用于文档分类
"""

class ClassificationClient:
    """Qwen2.5-VL-7B 视觉模型客户端
    
    封装对 llama-server (Qwen2.5-VL-7B) 的 OpenAI 兼容 API 调用。
    用于：
    - VLMDocumentClassifier: 文档分类兜底
    
    注意：必须使用多模态模型（视觉语言模型），不能用纯文本模型
    """
```

#### 4. Pipeline 日志 (`pipeline.py`)

```python
# 修改前
logger.info(
    "[分类] %s | 方法=VLM兜底 | 模型=%s | 结果=%s | 耗时=%.2fs",
    Path(image_path).name, "Qwen3.5-4B", doc_info.doc_type.value, classify_time
)

# 修改后
logger.info(
    "[分类] %s | 方法=VLM兜底 | 模型=%s | 结果=%s | 耗时=%.2fs",
    Path(image_path).name, "Qwen2.5-VL-7B", doc_info.doc_type.value, classify_time
)
```

#### 5. 服务层元数据 (`service.py`)

```python
# 修改前
PIPELINE_STAGES = [
    {"id": "stage4", "name": "阶段4", "title": "VLM分类兜底", "keywords": "Qwen3.5-4B视觉识别"},
]

# 修改后
PIPELINE_STAGES = [
    {"id": "stage4", "name": "阶段4", "title": "VLM分类兜底", "keywords": "Qwen2.5-VL-7B视觉识别"},
]
```

#### 6. LLM 层配置 (`llm_layer.py`)

```python
# 修改前（默认配置与 config.py 不一致）
DEFAULT_CHAT_BOT_CONFIG = {
    "model_name": "qwen3.5:4b",  # 默认使用 Qwen3.5-4B
}

# 修改后（与 config.py 保持一致）
DEFAULT_CHAT_BOT_CONFIG = {
    "model_name": "qwen35-4b-test:latest",  # 使用 Qwen35-4B 测试版（Ollama）
}
```

---

## 验证方法

### 1. 检查服务状态

```bash
# 确认 Qwen2.5-VL-7B 在端口 8082 运行
curl http://localhost:8082/v1/models
```

### 2. 测试 VLM 分类

```python
from ocr_three_layer_hybrid.vlm_classifier import VLMDocumentClassifier

classifier = VLMDocumentClassifier()
doc_type, confidence, metadata = classifier.classify("test_image.jpg")

print(f"文档类型: {doc_type}")
print(f"置信度: {confidence}")
print(f"路由: {metadata.get('route')}")
```

### 3. 测试混合分类器

```python
from ocr_three_layer_hybrid.service import OCRService

service = OCRService()

# 测试一个规则分类器无法判定的文档
result = service.process_single("unknown_doc.jpg")

print(f"分类结果: {result['classification']['doc_type']}")
print(f"路由: {result['classification']['route']}")
print(f"VLM结果: {result['classification'].get('vlm_result')}")
```

---

## 预期效果

### 修复前

- ❌ VLM 分类兜底失效
- ❌ 无法处理规则分类器无法判定的文档
- ⚠️ 更多文档被标记为 UNKNOWN

### 修复后

- ✅ VLM 分类兜底正常工作
- ✅ 规则分类失败时，Qwen2.5-VL-7B 进行视觉分类
- ✅ 减少 UNKNOWN 类型文档数量
- ✅ 提升整体分类准确率

---

## 架构调整

### 修复前的服务端口

```
端口 8080: GLM-OCR (视觉模型) → VLM 字段提取 + OCR
端口 8081: Qwen3.5-4B (文本模型) → VLM 分类 ❌ 错误
端口 8082: Qwen2.5-VL-7B (视觉模型) → VLM 字段提取
端口 11434: Ollama (Qwen35-4B) → LLM 字段提取
```

### 修复后的服务端口

```
端口 8080: GLM-OCR (视觉模型) → VLM 字段提取 + OCR
端口 8082: Qwen2.5-VL-7B (视觉模型) → VLM 分类 ✅ + VLM 字段提取
端口 11434: Ollama (Qwen35-4B) → LLM 字段提取
```

**优势**：
- 减少一个服务（不再需要端口 8081 的 Qwen3.5-4B）
- 统一使用视觉模型处理视觉任务
- 架构更清晰，职责更明确

---

## 注意事项

1. **端口 8081 不再使用**：可以停止该服务，释放资源
2. **Qwen2.5-VL-7B 负载增加**：现在同时处理分类和提取任务，需监控性能
3. **测试覆盖**：建议运行完整评测验证修复效果

---

## 相关文件

- `src/ocr_three_layer_hybrid/config.py`
- `src/ocr_three_layer_hybrid/vlm_classifier.py`
- `src/ocr_three_layer_hybrid/external_services.py`
- `src/ocr_three_layer_hybrid/pipeline.py`
- `src/ocr_three_layer_hybrid/service.py`
- `src/ocr_three_layer_hybrid/llm_layer.py`

---

## 修复日期

2026-07-01
