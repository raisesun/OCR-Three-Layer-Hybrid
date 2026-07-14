# OCR 三层混合架构 - 代码流程与技术栈

## 架构概述

**核心理念**：分层处理，每层使用最适合的技术栈，兼顾速度、准确率和成本。

```
输入图片 → OCR文本提取 → 文档分类 → 字段提取（三层） → 输出结果
                              ↓
                    规则层 → VLM层 → LLM层
```

---

## 流程节点详解

### 节点1：OCR 文本提取

**技术栈**：
- **主引擎**：PP-OCRv6 (PaddleOCR)
  - 模型：PP-OCRv6_medium_det + PP-OCRv6_medium_rec
  - 耗时：约 12-42 秒/张
  - 特点：CPU 推理，稳定可靠
  
- **备用引擎**：PaddleOCR-VL (视觉语言模型)
  - 模型：PaddleOCR-VL
  - 耗时：约 151 秒/张
  - 特点：精度高但速度慢，用于 PP-OCRv6 效果不佳的文档

- **分层策略**（已弃用）：
  - 先用 PP-OCRv6（快速）
  - 如果文本 < 100 字，切换 PaddleOCR-VL（精度高）
  - 实测准确率下降且速度变慢，不推荐

**代码位置**：
- `service.py` 第 232-304 行：`run_ocr()` 方法
- `paddleocr_wrapper.py`：PaddleOCR 封装

**配置**：
```python
# config.py
ocr_engine: str = "ppocr"  # "ppocr" | "glm_ocr" | "paddleocr_vl" | "structure_v3"
```

---

### 节点2：文档分类

**技术栈**：混合分类器（规则优先 + VLM 兜底）

#### 2.1 规则分类器（KeywordDocumentClassifier）

**技术**：基于关键词的多阶段路由

**路由逻辑**（按优先级）：

**阶段0：多文档冲突检测**
- 信号：买受人 + 出卖人 + 房屋类型
- 场景：一份文档包含多个合同（如购房合同 + 资金监管协议）

**阶段1：标准证件强信号**
- 身份证：公民身份号码、签发机关
- 户口本：常住人口登记卡
- 结婚证：结婚证字号
- 离婚证：离婚证字号
- 房产证：不动产权证书、BDCQZ

**阶段1.5：备选强信号（组合匹配）**
- 结婚证：持证人 + 登记日期
- 户口本：户口簿 + 户主
- 身份证：公民身份 + 18位身份证号模式

**阶段1.6：更多备选信号**
- 户口本首页：户别 + 户主姓名 + (住址 或 户口专用章)
- 结婚证盖章页：结婚证 + 登记机关
- 房产证附记页：不动产权 + 权利人 + 不动产单元号

**阶段2：标准单证强信号**
- 发票：发票代码 + 发票号码

**阶段3：合同/协议字段组合**
- 购房合同：买受人 + 出卖人 + 总价款 + 商品房
- 存量房合同：买受人 + 出卖人 + 总价款 + 存量房
- 资金监管协议：资金监管 + 监管金额
- 离婚协议：离婚 + 财产分割/抚养

**阶段4：VLM 分类兜底**
- 触发条件：规则层无法判定（返回 UNKNOWN）
- 使用 VLM 视觉识别文档类型

**代码位置**：
- `classifier.py`：KeywordDocumentClassifier
- `vlm_classifier.py`：VLMDocumentClassifier, HybridDocumentClassifier

**性能**：
- 规则分类：毫秒级
- VLM 兜底：约 20-30 秒

---

#### 2.2 VLM 分类器（备用）

**技术**：Qwen3.5-4B 视觉语言模型

**模型配置**：
- 模型：Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
- 服务：llama-server (端口 8081)
- 耗时：约 20-30 秒

**Prompt**：
```
请识别这张图片是什么类型的文档。
可选类型：身份证、户口本、结婚证、离婚证、不动产权证书、发票、购房合同、存量房买卖合同、资金监管协议、离婚协议、附属页面。
只输出文档类型名称，不要输出其他内容。
```

**代码位置**：
- `vlm_classifier.py`：VLMDocumentClassifier

---

### 节点3：字段提取（三层架构）

**路由策略**：根据文档类型选择最优提取层

```python
# pipeline.py 第 76-88 行
DEFAULT_LAYER_ROUTING = {
    ID_CARD: RULE,              # 身份证 → 规则层
    MARRIAGE_CERTIFICATE: RULE, # 结婚证 → 规则层
    HOUSEHOLD_REGISTER: RULE,   # 户口本 → 规则层
    INVOICE: RULE,              # 发票 → 规则层
    FUND_SUPERVISION: RULE,     # 资金监管协议 → 规则层
    DIVORCE_AGREEMENT: RULE,    # 离婚协议 → 规则层
    
    DIVORCE_CERTIFICATE: VLM,   # 离婚证 → VLM层
    UNKNOWN: VLM,               # 未知类型 → VLM层
    
    PROPERTY_CERTIFICATE: LLM,  # 不动产权证书 → LLM层
    PURCHASE_CONTRACT: LLM,     # 购房合同 → LLM层
    STOCK_CONTRACT: LLM,        # 存量房合同 → LLM层
}
```

---

#### 3.1 规则层（Rule Layer）

**技术**：正则表达式 + 位置标注提取

**适用文档**：
- 身份证、结婚证、户口本、发票、资金监管协议、离婚协议

**核心技术**：

**3.1.1 位置标注提取器（HouseholdPositionExtractor）**
- 用途：户口本首页字段提取
- 技术：PaddleOCR 坐标位置感知
- 原理：利用 OCR 返回的文本坐标，根据位置关系提取字段
- 优势：抗 OCR 噪声干扰，准确率高

**代码位置**：
- `rule_layer.py`：RuleExtractionLayer
- `position_extractor.py`：HouseholdPositionExtractor

**提取示例**（户口本首页）：
```python
# 第1步：位置标注提取（优先）
if doc_type == HOUSEHOLD_REGISTER and is_front_page:
    pos_fields = position_extractor.extract(image_path)
    # 提取：户别、户主姓名、户号、住址

# 第2步：正则提取（补充）
regex_fields = {
    "姓名": r"姓\s*名\s*([^\s]+)",
    "公民身份号码": r"公民身份号码\s*(\d{17}[\dXx])",
    "与户主关系": r"与户主关系\s*([^\s]+)",
}
```

**性能**：
- 耗时：毫秒级
- 准确率：100%（10/10 样本）

---

#### 3.2 VLM 层（Vision-Language Model Layer）

**技术**：视觉语言模型直接提取字段

**适用文档**：
- 离婚证、未知类型文档
- 规则层提取失败的文档（兜底）

**模型配置**：
- **主选**：Qwen2.5-VL-7B（推荐）
  - 服务：llama-server (端口 8082)
  - 耗时：约 40 秒/张
  - 优势：理解能力强，速度快
  
- **备选**：GLM-OCR
  - 服务：llama-server (端口 8080)
  - 耗时：约 60 秒/张
  - 优势：速度快但理解能力稍弱

**Prompt 设计**：
```python
# 户口本示例
PROMPT = """
你是一名专业的户口本页信息提取专家。请仔细识别图片中的「常住人口登记卡」表格，
按以下 JSON 格式输出所有可识别的字段信息。

## 输出 JSON 格式
{
  "姓名": "",
  "户主": "",
  "与户主关系": "",
  "性别": "",
  "出生日期": "",
  "民族": "",
  "户籍地址": "",
  "公民身份号码": ""
}

## 重要注意事项
- 只输出纯 JSON，不要包含 markdown 代码块标记
- 如果某个字段不存在，保留为空字符串
"""
```

**代码位置**：
- `vlm_layer.py`：VLMExtractionLayer
- `external_services.py`：VLMClient

**性能**：
- 耗时：约 40-60 秒/张
- 准确率：100%（但提取字段数较少）

---

#### 3.3 LLM 层（Large Language Model Layer）

**技术**：PP-ChatOCRv4 + 向量检索 + LLM

**适用文档**：
- 购房合同、存量房合同、不动产权证书
- 复杂文档（多页、非固定格式）

**核心技术**：

**3.3.1 PP-ChatOCRv4**
- 框架：PaddleOCR 官方文档理解框架
- 流程：
  1. **视觉信息提取**：使用 OCR 提取文本和布局信息
  2. **向量检索**：将 OCR 文本分块，构建向量索引
  3. **LLM 问答**：针对每个字段，检索相关文本块，调用 LLM 提取答案

**3.3.2 LLM 配置**
- 模型：Qwen35-4B (qwen35-4b-test:latest)
- 服务：Ollama (端口 11434)
- 耗时：约 30 秒/张

**3.3.3 向量检索模型**
- 模型：nomic-embed-text
- 服务：Ollama (端口 11434)
- 用途：将 OCR 文本分块后构建向量索引，用于检索相关文本

**代码位置**：
- `llm_layer.py`：PPChatOCRv4Layer

**性能**：
- 耗时：约 30 秒/张
- 准确率：待优化（购房合同成功率 22% → 目标 70%+）

---

### 节点4：VLM 字段级兜底

**技术**：VLM 重新提取校验失败的字段

**触发条件**：
1. 规则层或 VLM 层提取成功
2. 字段校验器检测到某些字段无效（如身份证号校验失败）
3. 文档类型启用 VLM 兜底（户口本、结婚证、身份证）

**流程**：
```python
# 1. 字段校验
failed_fields = validator.get_failed_fields(fields)
# 例如：{"公民身份号码": "12345"} → 校验失败

# 2. VLM 重新提取
vlm_fields = vlm_fallback_handler.fallback_extract(
    image_path=image_path,
    failed_fields=["公民身份号码"],
    doc_type=DocumentType.HOUSEHOLD_REGISTER
)

# 3. 合并结果
for field in failed_fields:
    if vlm_fields.get(field):
        fields[field] = vlm_fields[field]
```

**字段校验规则**：
- 身份证号：18位，校验码验证
- 日期格式：YYYY-MM-DD 或 YYYY年MM月DD日
- 金额：数字格式验证

**代码位置**：
- `vlm_fallback.py`：VLMFallbackHandler
- `field_validator.py`：FieldValidator

**性能**：
- 触发率：低（大多数情况下规则层已足够）
- 耗时：约 20 秒（仅在触发时）

---

### 节点5：多页文档处理（性能优化）

**技术**：批量处理 + 字段合并

**适用文档**：
- 购房合同（50+ 页）
- 存量房合同（30+ 页）

**优化策略**：
1. **限制处理页数**：只处理前 15 页（性能优化）
2. **字段合并**：遍历每页，合并提取到的字段（保留最长值）
3. **并行处理**：可选（当前未实现）

**代码位置**：
- `vlm_model_evaluation.py`：`process_multi_page_document()` 函数

**性能**：
- 单页耗时：约 40-60 秒
- 15 页总耗时：约 10-15 分钟
- 字段完整性：显著提升（从 0.6 字段 → 目标 4+ 字段）

---

## 技术栈总结

### 大模型清单

| 模型 | 用途 | 服务 | 端口 | 耗时 |
|------|------|------|------|------|
| **PP-OCRv6** | OCR 文本提取 | PaddleOCR | - | 12-42s |
| **PaddleOCR-VL** | OCR 备用 | PaddleOCR | - | 151s |
| **Qwen3.5-4B** | VLM 分类兜底 | llama-server | 8081 | 20-30s |
| **Qwen2.5-VL-7B** | VLM 字段提取（主选） | llama-server | 8082 | 40s |
| **GLM-OCR** | VLM 字段提取（备选） | llama-server | 8080 | 60s |
| **Qwen35-4B** | LLM 字段提取 | Ollama | 11434 | 30s |
| **nomic-embed-text** | 向量检索 | Ollama | 11434 | <1s |

### 核心技术

| 技术 | 用途 | 优势 |
|------|------|------|
| **正则表达式** | 规则层字段提取 | 速度快（毫秒级），准确率高（100%） |
| **PaddleOCR 坐标** | 位置标注提取 | 抗 OCR 噪声，适合固定格式文档 |
| **VLM Prompt 工程** | VLM 层字段提取 | 理解能力强，适合半固定文档 |
| **PP-ChatOCRv4** | LLM 层字段提取 | 向量检索 + LLM，适合复杂文档 |
| **混合分类器** | 文档分类 | 规则优先（快）+ VLM 兜底（准） |
| **字段校验 + VLM 兜底** | 字段级纠错 | 自动检测并修复错误字段 |

---

## 性能指标（50 样本评测）

### 优化前（单页处理）

| 指标 | GLM-OCR | Qwen2.5-VL-7B |
|------|---------|---------------|
| 成功率 | 82% | 82% |
| 平均字段数 | 2.2 | 2.2 |
| 字段准确率 | 75% | 75% |
| 平均耗时 | 61.4s | 39.9s |

### 按文档类型（优化前）

| 文档类型 | 成功率 | 平均字段数 | 问题 |
|---------|--------|-----------|------|
| 身份证 | 100% | 3.5 | ✅ 表现良好 |
| 户口本 | 100% | 3.5 | ✅ 表现良好 |
| 结婚证 | 100% | 3.0 | ✅ 表现良好 |
| 发票 | 100% | 4.0 | ✅ 表现良好 |
| 不动产权证书 | 75% | 0.2 | ⚠️ 字段提取不完整 |
| 存量房合同 | 50% | 3.0 | ⚠️ 部分失败 |
| 购房合同 | 22% | 0.6 | ❌ 单页处理导致 |

### 优化后（预期）

**改进点**：
1. ✅ LLM 层配置完成（PP-ChatOCRv4 + Qwen35-4B）
2. ✅ 多页文档处理（购房合同处理前 15 页）
3. ✅ 位置标注提取器集成（户口本首页）
4. ✅ VLM 兜底机制验证（字段校验失败时触发）

**预期指标**：
- 购房合同成功率：22% → 70%+
- 平均字段数：2.2 → 3.5+
- 推荐生产环境 VLM 引擎：**Qwen2.5-VL-7B**（速度快 35%）

---

## 代码架构

```
src/ocr_three_layer_hybrid/
├── config.py                 # 配置管理
├── service.py                # 统一服务接口
├── pipeline.py               # Pipeline 编排（PlanEPlusPipeline）
├── classifier.py             # 规则分类器
├── vlm_classifier.py         # VLM 分类器 + 混合分类器
├── rule_layer.py             # 规则层（正则 + 位置标注）
├── position_extractor.py     # 位置标注提取器
├── vlm_layer.py              # VLM 层
├── llm_layer.py              # LLM 层（PP-ChatOCRv4）
├── vlm_fallback.py           # VLM 字段级兜底
├── field_validator.py        # 字段校验器
├── external_services.py      # 外部服务客户端（VLMClient）
├── paddleocr_wrapper.py      # PaddleOCR 封装
└── interfaces.py             # 接口定义（DocumentType, ProcessingLayer 等）
```

---

## 关键流程示例

### 示例1：户口本首页处理

```python
# 1. OCR 文本提取
ocr_text = service.run_ocr("hukou_front.jpg")  # PP-OCRv6, 12s

# 2. 文档分类
doc_info = classifier.classify("hukou_front.jpg", [ocr_text])
# → HOUSEHOLD_REGISTER, route="standard_certificate"

# 3. 字段提取（规则层）
# 3.1 位置标注提取（优先）
pos_fields = position_extractor.extract("hukou_front.jpg")
# → {"户别": "农村家庭户", "户主姓名": "张三", "户号": "123456", "住址": "安徽省蚌埠市..."}

# 3.2 正则提取（补充）
regex_fields = {
    "姓名": "张三",
    "公民身份号码": "340322199403014698",
    "与户主关系": "户主",
}

# 3.3 合并结果
fields = {**pos_fields, **regex_fields}

# 4. 字段校验
failed = validator.get_failed_fields(fields)
# → [] (全部通过)

# 5. 输出结果
result = {
    "doc_type": "household_register",
    "layer": "rule",
    "fields": fields,
    "success": True,
}
```

**总耗时**：约 12-15 秒

---

### 示例2：购房合同处理（多页）

```python
# 1. 遍历合同文件夹
folder = "/path/to/contract_202406240010/"
images = sorted(os.listdir(folder))[:15]  # 只处理前 15 页

# 2. 逐页处理
merged_fields = {}
for img in images:
    # 2.1 OCR 文本提取
    ocr_text = service.run_ocr(img)  # PP-OCRv6, 12s
    
    # 2.2 文档分类
    doc_info = classifier.classify(img, [ocr_text])
    # → PURCHASE_CONTRACT
    
    # 2.3 字段提取（LLM 层）
    result = llm_layer.extract(doc_info, key_list)
    # → PP-ChatOCRv4 + Qwen35-4B, 30s
    
    # 2.4 合并字段（保留最长值）
    for key, value in result.fields.items():
        if value and (key not in merged_fields or len(value) > len(merged_fields[key])):
            merged_fields[key] = value

# 3. 输出结果
result = {
    "doc_type": "purchase_contract",
    "layer": "llm",
    "fields": merged_fields,
    "pages_processed": 15,
    "success": True,
}
```

**总耗时**：约 10-15 分钟（15 页）

---

## 配置说明

### 环境变量

```bash
# OCR 引擎
export OCR_ENGINE=ppocr  # ppocr | glm_ocr | paddleocr_vl

# VLM 提取引擎
export VLM_EXTRACTION_ENGINE=qwen2_5_vl_7b  # qwen2_5_vl_7b | glm_ocr

# 服务地址
export GLM_OCR_URL=http://localhost:8080/v1
export QWEN_VLM_URL=http://localhost:8082/v1
export OLLAMA_URL=http://localhost:11434/v1
```

### Python 配置

```python
from ocr_three_layer_hybrid.config import OCRConfig

config = OCRConfig()
config.ocr_engine = "ppocr"
config.vlm_extraction_engine = "qwen2_5_vl_7b"
config.enable_vlm_fallback = True
config.enable_position_extraction = True
config.enable_vlm_field_fallback = True

service = OCRService(config=config)
```

---

## 总结

**架构优势**：
1. ✅ **分层处理**：每层使用最适合的技术，兼顾速度和准确率
2. ✅ **规则优先**：简单文档用正则（毫秒级），复杂文档用 VLM/LLM
3. ✅ **多级兜底**：规则 → VLM → LLM → VLM 字段级兜底
4. ✅ **可扩展**：易于添加新文档类型和提取规则

**性能瓶颈**：
1. ⚠️ LLM 层耗时长（30 秒/张），影响购房合同等多页文档
2. ⚠️ 购房合同成功率低（22%），需要多页处理优化
3. ⚠️ 不动产权证书字段提取不完整（平均 0.2 字段）

**优化方向**：
1. ✅ 多页文档处理（已实现，待验证）
2. ⏳ LLM 层性能优化（批处理、并行化）
3. ⏳ 不动产权证书提取优化（增强 Prompt 或规则）
4. ⏳ 生产环境部署（性能基准测试、错误处理）
