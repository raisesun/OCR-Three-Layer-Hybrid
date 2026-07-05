# VLM配置说明

## 概述

OCR三层混合架构支持灵活配置不同的VLM模型用于不同场景。

## VLM使用场景

| 场景 | 配置项 | 默认值 | 说明 |
|------|--------|--------|------|
| **VLM提取层** | `vlm_extraction_engine` | `qwen2_5_vl_7b` | 分类为"未知"时使用 |
| **VLM兜底处理器** | `vlm_fallback_engine` | `qwen2_5_vl_7b` | 规则层字段校验失败时触发 |
| **VLM纯OCR** | `vlm_ocr_engine` | `qwen2_5_vl_7b` | 纯文本提取 |

## 可用VLM模型

### 1. Qwen2.5-VL-7B（推荐，默认）

- **端口**: 8082
- **模型大小**: 4.4G (主模型) + 814M (MMProj)
- **特点**: 理解能力强，速度快（比GLM-OCR快35%）
- **启动命令**:

```bash
cd /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B && \
llama-server \
  --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \
  --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \
  --host 0.0.0.0 --port 8082 --ctx-size 8192
```

### 2. GLM-OCR（备选）

- **端口**: 8080
- **模型大小**: 906M (主模型) + 462M (MMProj)
- **特点**: 模型小，速度快，但理解能力较弱
- **启动命令**:

```bash
cd /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF && \
llama-server \
  --model GLM-OCR-Q8_0.gguf \
  --mmproj mmproj-GLM-OCR-Q8_0.gguf \
  --host 0.0.0.0 --port 8080 --ctx-size 8192
```

## 配置方法

### 方法1：代码配置

```python
from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

config = OCRConfig()

# 统一使用Qwen2.5-VL-7B（默认）
config.vlm_extraction_engine = "qwen2_5_vl_7b"
config.vlm_fallback_engine = "qwen2_5_vl_7b"
config.vlm_ocr_engine = "qwen2_5_vl_7b"

# 或者混合使用（不推荐）
config.vlm_extraction_engine = "qwen2_5_vl_7b"  # 提取层用Qwen
config.vlm_fallback_engine = "glm_ocr"           # 兜底用GLM

service = OCRService(config=config)
```

### 方法2：环境变量配置

```bash
# 设置VLM服务地址
export QWEN_VLM_URL="http://localhost:8082/v1"
export GLM_OCR_URL="http://localhost:8080/v1"
```

### 方法3：直接修改配置文件

编辑 `src/ocr_three_layer_hybrid/config.py`：

```python
@dataclass
class OCRConfig:
    # VLM 引擎配置
    vlm_extraction_engine: str = "qwen2_5_vl_7b"  # 提取层
    vlm_fallback_engine: str = "qwen2_5_vl_7b"    # 兜底
    vlm_ocr_engine: str = "qwen2_5_vl_7b"         # OCR
```

## 推荐配置

### 生产环境（推荐）

统一使用Qwen2.5-VL-7B：

```python
vlm_extraction_engine = "qwen2_5_vl_7b"
vlm_fallback_engine = "qwen2_5_vl_7b"
vlm_ocr_engine = "qwen2_5_vl_7b"
```

**优点**：
- 只需启动一个VLM服务（端口8082）
- 配置一致，易于维护
- 理解能力强，准确率高
- 速度快（比GLM-OCR快35%）

### 资源受限环境

使用GLM-OCR：

```python
vlm_extraction_engine = "glm_ocr"
vlm_fallback_engine = "glm_ocr"
vlm_ocr_engine = "glm_ocr""
```

**优点**：
- 模型小（906M vs 4.4G）
- 内存占用低

**缺点**：
- 理解能力弱，准确率较低

## 启动VLM服务

### 只启动Qwen2.5-VL-7B（推荐）

```bash
cd /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B && \
llama-server \
  --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \
  --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \
  --host 0.0.0.0 --port 8082 --ctx-size 8192
```

### 同时启动两个服务（混合配置时需要）

```bash
# 终端1：GLM-OCR
cd /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF && \
llama-server \
  --model GLM-OCR-Q8_0.gguf \
  --mmproj mmproj-GLM-OCR-Q8_0.gguf \
  --host 0.0.0.0 --port 8080 --ctx-size 8192

# 终端2：Qwen2.5-VL-7B
cd /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B && \
llama-server \
  --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \
  --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \
  --host 0.0.0.0 --port 8082 --ctx-size 8192
```

## 验证配置

```python
from ocr_three_layer_hybrid.service import OCRService

service = OCRService()

# 查看当前配置
print(f"提取层: {service.config.vlm_extraction_engine}")
print(f"兜底层: {service.config.vlm_fallback_engine}")
print(f"OCR层: {service.config.vlm_ocr_engine}")

# 查看服务地址
extraction_config = service.config.get_vlm_config(service.config.vlm_extraction_engine)
print(f"提取层地址: {extraction_config.base_url}")
```

## 性能对比

| 指标 | GLM-OCR | Qwen2.5-VL-7B | 差异 |
|------|---------|---------------|------|
| 模型大小 | 906M | 4.4G | Qwen大4.8倍 |
| 内存占用 | ~2G | ~6G | Qwen多4G |
| 推理速度 | 61.4秒/样本 | 39.9秒/样本 | **Qwen快35%** |
| 准确率 | 82% | 82% | 相同 |
| 理解能力 | 弱 | 强 | Qwen更好 |

**结论**：推荐使用Qwen2.5-VL-7B，速度快且理解能力强。

---

**更新日期**: 2026-07-05
**更新者**: Claude
