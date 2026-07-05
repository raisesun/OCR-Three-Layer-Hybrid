# VLM服务使用分析

## 问题发现

在检查VLM服务配置时，发现存在不一致的使用情况。

## 当前架构

### VLM使用场景

| 场景 | 配置项 | 默认值 | 端口 | 说明 |
|------|--------|--------|------|------|
| **VLM提取层** | `vlm_extraction_engine` | `qwen2_5_vl_7b` | 8082 | 分类为"未知"时使用 |
| **VLM兜底处理器** | `vlm_service` | `glm_ocr` | 8080 | 字段校验失败时触发 |
| **VLM客户端** | `vlm_service` | `glm_ocr` | 8080 | 被VLM兜底使用 |

### 代码位置

#### 1. VLM提取层（正确）

```python
# service.py 第150-157行
vlm_extraction_engine = self.config.vlm_extraction_engine
if vlm_extraction_engine == "qwen2_5_vl_7b":
    vlm_service_config = self.config.qwen_vl_service  # 端口8082
    logger.info(f"VLM 提取层使用: Qwen2.5-VL-7B ({vlm_service_config.base_url})")
else:  # 默认使用 glm_ocr
    vlm_service_config = self.config.vlm_service  # 端口8080
    logger.info(f"VLM 提取层使用: GLM-OCR ({vlm_service_config.base_url})")
```

**配置**：`vlm_extraction_engine = "qwen2_5_vl_7b"`（默认）
**端口**：8082 ✅

#### 2. VLM兜底处理器（不一致）

```python
# service.py 第121行
self._vlm_client = VLMClient(self.config.vlm_service)  # 使用GLM-OCR配置

# service.py 第141行
self._vlm_fallback_handler = VLMFallbackHandler(vlm_client=self._vlm_client)
```

**配置**：`vlm_service`（默认GLM-OCR）
**端口**：8080 ❌

#### 3. 配置文件说明

```python
# config.py 第14-35行
@dataclass
class VLMServiceConfig:
    """GLM-OCR 视觉模型服务配置（端口8080）"""
    base_url: str = "http://localhost:8080/v1"
    model_name: str = "GLM-OCR-Q8_0.gguf"

# config.py 第38-59行
@dataclass
class QwenVLServiceConfig:
    """Qwen2.5-VL-7B 视觉模型服务配置（端口8082）"""
    base_url: str = "http://localhost:8082/v1"
    model_name: str = "qwen2.5-vl-7b"

# config.py 第94行
vlm_extraction_engine: str = "qwen2_5_vl_7b"  # 默认使用Qwen
```

## 问题分析

### 不一致之处

1. **VLM提取层**使用Qwen2.5-VL-7B（端口8082）✅
2. **VLM兜底处理器**使用GLM-OCR（端口8080）❌

### 影响

- 如果只启动Qwen2.5-VL-7B服务，VLM兜底功能会失败
- 两个VLM模型同时运行会增加资源消耗
- 配置不一致增加维护成本

### 根因

- `service.py`第121行硬编码使用`self.config.vlm_service`（GLM-OCR）
- 没有根据`vlm_extraction_engine`配置动态选择VLM客户端

## 解决方案

### 方案A：统一使用Qwen2.5-VL-7B（推荐）

**修改service.py第121行**：

```python
# 修改前
self._vlm_client = VLMClient(self.config.vlm_service)

# 修改后
if self.config.vlm_extraction_engine == "qwen2_5_vl_7b":
    vlm_client_config = self.config.qwen_vl_service
else:
    vlm_client_config = self.config.vlm_service
self._vlm_client = VLMClient(vlm_client_config)
```

**优点**：
- 统一使用一个VLM模型，减少资源消耗
- 配置一致，易于维护
- Qwen2.5-VL-7B理解能力更强

**缺点**：
- 需要修改代码

### 方案B：保持现状，同时启动两个服务

**不修改代码**，同时启动GLM-OCR和Qwen2.5-VL-7B。

**优点**：
- 无需修改代码

**缺点**：
- 需要同时运行两个VLM服务，增加资源消耗
- 配置不一致，增加维护成本
- 不符合"已替换为Qwen2.5-VL-7B"的预期

## 推荐方案

**方案A：统一使用Qwen2.5-VL-7B**

理由：
1. 符合"已替换为Qwen2.5-VL-7B"的预期
2. 减少资源消耗（只需运行一个VLM服务）
3. Qwen2.5-VL-7B理解能力更强（根据50样本测试）
4. 配置一致，易于维护

## 下一步

1. 修改`service.py`第121行，统一使用Qwen2.5-VL-7B
2. 更新文档，说明只需要启动Qwen2.5-VL-7B服务
3. 重新运行回归测试

---

**创建日期**：2026-07-05
**创建者**：Claude
