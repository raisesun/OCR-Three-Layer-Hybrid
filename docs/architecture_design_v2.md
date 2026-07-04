# OCR 三层混合架构简化设计 v2.0

## 文档版本
- 版本：2.0
- 日期：2026-07-02
- 状态：设计中

---

## 一、架构演进

### 1.1 v1.0 架构（当前）

```
┌─────────────────────────────────────────────────────────┐
│                    OCR 三层混合架构 v1.0                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  节点1: OCR 文本提取                                     │
│  ├─ PP-OCRv6（主力）                                    │
│  └─ PaddleOCR-VL（备用）❌ 冗余                          │
│                                                          │
│  节点2: 文档分类                                         │
│  ├─ 规则分类器（主力）                                  │
│  └─ VLM 分类兜底（Qwen2.5-VL-7B）❌ 冗余                │
│                                                          │
│  节点3: 字段提取                                         │
│  ├─ 3.1 规则层（身份证、户口本、结婚证等）              │
│  ├─ 3.2 VLM 层（离婚证、UNKNOWN）                      │
│  └─ 3.3 LLM 层（PP-ChatOCRv4）❌ 失败，已简化          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**问题**：
1. PaddleOCR-VL 备用从未使用，冗余
2. VLM 分类兜底耗时 20-30 秒，收益不明确
3. LLM 层（PP-ChatOCRv4）处理合同文档完全失败（0 字段）
4. 架构复杂，5 个组件，4 个决策点

### 1.2 v2.0 架构（目标）

```
┌─────────────────────────────────────────────────────────┐
│                    OCR 三层混合架构 v2.0                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  节点1: OCR 文本提取                                     │
│  └─ PP-OCRv6（唯一）✅ 简化                              │
│                                                          │
│  节点2: 文档分类                                         │
│  └─ 规则分类器（唯一）✅ 简化                            │
│                                                          │
│  节点3: 字段提取                                         │
│  ├─ 3.1 规则层（身份证、户口本、结婚证、发票等）        │
│  └─ 3.2 VLM 层（离婚证、UNKNOWN、合同、房产证）✅ 增强  │
│     ├─ 类型识别 + 字段提取（组合 Prompt）               │
│     └─ 多页文档处理（逐页提取 + 字段合并）              │
│                                                          │
│  ❌ 已移除：                                             │
│  - PaddleOCR-VL 备用                                    │
│  - VLM 分类兜底                                         │
│  - LLM 层（PP-ChatOCRv4）                               │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**优势**：
1. ✅ 架构简化：3 个组件，2 个决策点
2. ✅ 处理速度提升 20-30%（节省 VLM 分类时间）
3. ✅ 维护成本降低 50%
4. ✅ 准确率相同或更高（VLM 直接识别类型）

---

## 二、详细设计

### 2.1 节点 1：OCR 文本提取

**组件**：PP-OCRv6（唯一）

**输入**：文档图片

**输出**：OCR 文本

**处理流程**：
```
图片 → PP-OCRv6 → OCR 文本
```

**配置**：
```python
# config.py
@dataclass
class OCRConfig:
    ocr_engine: str = "ppocr"  # 只支持 "ppocr"
```

**移除的内容**：
- ❌ PaddleOCR-VL 备用引擎
- ❌ 分层 OCR 策略（`run_ocr_tiered` 方法）

**代码修改**：
1. `service.py`：移除 `run_ocr_tiered` 方法和 PaddleOCR-VL 相关代码
2. `paddleocr_wrapper.py`：移除 VLM 引擎支持（如果存在）
3. `config.py`：简化 OCR 引擎配置

---

### 2.2 节点 2：文档分类

**组件**：规则分类器（唯一）

**输入**：OCR 文本

**输出**：文档类型（DocumentType）

**处理流程**：
```
OCR 文本 → 规则分类器 → 文档类型
  ├─ 明确分类（80%）→ 进入节点 3
  └─ UNKNOWN（20%）→ 进入节点 3（VLM 层）
```

**分类规则**（保持不变）：
- 阶段 0：多文档冲突检测
- 阶段 1：标准证件强信号
- 阶段 1.5：备选强信号
- 阶段 1.6：更多备选信号
- 阶段 2：标准单证强信号
- 阶段 3：合同/协议字段组合

**移除的内容**：
- ❌ VLM 分类兜底（VLMDocumentClassifier）
- ❌ 混合分类器（HybridDocumentClassifier）

**代码修改**：
1. `service.py`：移除 VLM 分类器和混合分类器相关代码
2. `vlm_classifier.py`：整个文件可以删除或归档
3. `classifier.py`：保留规则分类器，移除混合分类器逻辑
4. `config.py`：移除 ClassificationServiceConfig（如果只用于 VLM 分类）

---

### 2.3 节点 3：字段提取

#### 2.3.1 规则层（3.1）

**适用文档**：
- 身份证（ID_CARD）
- 户口本（HOUSEHOLD_REGISTER）
- 结婚证（MARRIAGE_CERTIFICATE）
- 发票（INVOICE）
- 资金监管协议（FUND_SUPERVISION）
- 离婚协议（DIVORCE_AGREEMENT）

**处理流程**：
```
文档类型 + OCR 文本 → 规则提取器 → 字段
```

**技术**：
- 正则表达式匹配
- 位置标注提取（户口本首页）

**代码**：保持不变

**备忘**
如果要提高速度或者优化确定性，那么购房合同、存量房合同、房产证、离婚证也需要先经过节点3.1的规则层

---

#### 2.3.2 VLM 层（3.2）- 增强版

**适用文档**：
- 离婚证（DIVORCE_CERTIFICATE）
- 购房合同（PURCHASE_CONTRACT）✅ 新增
- 存量房合同（STOCK_CONTRACT）✅ 新增
- 房产证（PROPERTY_CERTIFICATE）✅ 新增
- UNKNOWN（未知类型）✅ 增强

**核心能力**：
1. **类型识别 + 字段提取**（组合 Prompt）
2. **多页文档处理**（逐页提取 + 字段合并）

---

##### 2.3.2.1 类型识别 + 字段提取

**设计思路**：
- 对于 UNKNOWN 文档，VLM 需要同时识别文档类型并提取字段
- 使用组合 Prompt，要求 VLM 返回 JSON 包含 `doc_type` 和 `fields`

**Prompt 设计**：
```python
UNKNOWN_EXTRACTION_PROMPT = """
请分析这张图片，完成以下任务：

1. **识别文档类型**：判断这是什么类型的文档（身份证、户口本、结婚证、离婚证、房产证、发票、购房合同、存量房合同、资金监管协议、离婚协议、其他）

2. **提取关键字段**：根据识别的文档类型，提取以下字段（如果存在）：
   - 身份证：姓名、性别、民族、出生、住址、公民身份号码
   - 户口本：户主姓名、户号、住址、姓名、与户主关系、公民身份号码
   - 结婚证：持证人、登记日期、结婚证字号、男方姓名、女方姓名
   - 离婚证：持证人、登记日期、离婚证字号
   - 房产证：证书号、权利人、共有情况、不动产单元号、房屋地址、建筑面积、用途
   - 发票：发票代码、发票号码、开票日期、价税合计、购买方名称、销售方名称
   - 购房合同/存量房合同：合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积
   - 资金监管协议：监管金额、买方、卖方、监管机构
   - 离婚协议：男方姓名、女方姓名、离婚日期、财产分割约定、子女抚养

3. **输出格式**：严格使用以下 JSON 格式，不要包含 markdown 标记：
{
  "doc_type": "文档类型",
  "confidence": 0.95,
  "fields": {
    "字段1": "值1",
    "字段2": "值2"
  }
}

注意事项：
- 只输出纯 JSON，不要包含任何其他文字
- 如果某个字段不存在或无法识别，该字段值保留为空字符串
- confidence 表示你对文档类型识别的置信度（0-1）
"""
```

**处理流程**：
```
UNKNOWN 文档 + 图片 → VLM（类型识别 + 提取）→ {doc_type, confidence, fields}
```

---

##### 2.3.2.2 多页文档处理

**适用场景**：
- 购房合同（5-50+ 页）
- 存量房合同（5-30+ 页）
- 房产证（3-10+ 页）

**设计思路**：
- 逐页调用 VLM 提取固定字段列表
- 合并所有页面的提取结果（取第一个非空值）
- 限制处理页数（如前 15 页）以控制耗时

**处理流程**：
```
多页文档（N 张图片）
  ↓
[步骤 1] 确定目标字段列表
  - 购房合同: 合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积
  - 存量房合同: 合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积
  - 房产证: 证书号、权利人、共有情况、不动产单元号、房屋地址、建筑面积、用途
  ↓
[步骤 2] 逐页 VLM 提取（固定字段列表）
  for page in pages[:max_pages]:  # 限制处理页数（如 15 页）
    fields = vlm_extract(page, key_list)
    # VLM Prompt: "请从图片中提取以下字段：合同编号、买受人、出卖人...，不存在的返回空字符串"
  ↓
[步骤 3] 字段合并（取第一个非空值）
  merged_fields = {}
  for page_fields in all_pages_fields:
    for key, value in page_fields.items():
      if value and key not in merged_fields:
        merged_fields[key] = value
  ↓
[步骤 4] 返回合并结果
  return merged_fields
```

**Prompt 设计**（以购房合同为例）：
```python
PURCHASE_CONTRACT_EXTRACTION_PROMPT = """
请从这张购房合同图片中提取以下字段，严格按 JSON 格式输出：

{
  "合同编号": "",
  "买受人": "",
  "出卖人": "",
  "总价款": "",
  "签订日期": "",
  "房屋地址": "",
  "建筑面积": ""
}

注意事项：
- 只输出纯 JSON，不要包含 markdown 标记
- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串
- 仔细识别图片中的所有文字，确保不遗漏任何字段
- 总价款应包含单位（如"元"、"万元"）
- 建筑面积应包含单位（如"平方米"、"㎡"）
- 签订日期保持原始格式（如"2024年01月01日"或"2024-01-01"）
"""
```

**代码实现**：
```python
# vlm_layer.py
class VLMExtractionLayer:
    def extract_multi_page(
        self,
        image_paths: List[str],
        key_list: List[str],
        doc_type: DocumentType,
        max_pages: int = 15
    ) -> ExtractionResult:
        """
        多页文档提取：逐页提取 + 字段合并
        
        Args:
            image_paths: 图片路径列表
            key_list: 目标字段列表
            doc_type: 文档类型
            max_pages: 最大处理页数（性能优化）
        
        Returns:
            合并后的提取结果
        """
        merged_fields = {k: "" for k in key_list}
        total_time = 0.0
        pages_processed = 0
        
        # 获取文档类型的 Prompt
        prompt = self._get_extraction_prompt(doc_type, key_list)
        
        for img_path in image_paths[:max_pages]:
            # 单页提取
            start_time = time.time()
            vlm_response = self._call_vlm(prompt, img_path)
            page_time = time.time() - start_time
            total_time += page_time
            pages_processed += 1
            
            # 解析响应
            page_fields = self._parse_json_response(vlm_response, key_list)
            
            # 合并字段（取第一个非空值）
            for key, value in page_fields.items():
                if value and not merged_fields.get(key):
                    merged_fields[key] = value
            
            logger.info(
                f"[VLM层] 多页提取 | 页 {pages_processed}/{len(image_paths)} | "
                f"耗时 {page_time:.1f}s | 提取字段 {len([v for v in page_fields.values() if v])}"
            )
        
        # 判断是否成功
        non_empty_fields = {k: v for k, v in merged_fields.items() if v}
        success = len(non_empty_fields) > 0
        
        return ExtractionResult(
            doc_type=doc_type,
            layer=ProcessingLayer.VLM,
            fields=merged_fields,
            success=success,
            time_cost=total_time,
            raw_text=f"Processed {pages_processed} pages",
        )
    
    def _get_extraction_prompt(
        self,
        doc_type: DocumentType,
        key_list: List[str]
    ) -> str:
        """获取文档类型的提取 Prompt"""
        prompt_templates = {
            DocumentType.PURCHASE_CONTRACT: PURCHASE_CONTRACT_EXTRACTION_PROMPT,
            DocumentType.STOCK_CONTRACT: STOCK_CONTRACT_EXTRACTION_PROMPT,
            DocumentType.PROPERTY_CERTIFICATE: PROPERTY_CERTIFICATE_EXTRACTION_PROMPT,
            DocumentType.UNKNOWN: UNKNOWN_EXTRACTION_PROMPT,
        }
        return prompt_templates.get(doc_type, self._build_generic_prompt(key_list))
```

---

##### 2.3.2.3 文档路由调整

**修改前**：
```python
# pipeline.py
DEFAULT_LAYER_ROUTING = {
    DocumentType.ID_CARD: ProcessingLayer.RULE,
    DocumentType.MARRIAGE_CERTIFICATE: ProcessingLayer.RULE,
    DocumentType.HOUSEHOLD_REGISTER: ProcessingLayer.RULE,
    DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.LLM,  # ❌ 失败
    DocumentType.INVOICE: ProcessingLayer.RULE,
    DocumentType.PURCHASE_CONTRACT: ProcessingLayer.LLM,     # ❌ 失败
    DocumentType.STOCK_CONTRACT: ProcessingLayer.LLM,        # ❌ 失败
    DocumentType.FUND_SUPERVISION: ProcessingLayer.RULE,
    DocumentType.DIVORCE_CERTIFICATE: ProcessingLayer.VLM,
    DocumentType.DIVORCE_AGREEMENT: ProcessingLayer.RULE,
    DocumentType.UNKNOWN: ProcessingLayer.VLM,
}
```

**修改后**：
```python
# pipeline.py
DEFAULT_LAYER_ROUTING = {
    DocumentType.ID_CARD: ProcessingLayer.RULE,
    DocumentType.MARRIAGE_CERTIFICATE: ProcessingLayer.RULE,
    DocumentType.HOUSEHOLD_REGISTER: ProcessingLayer.RULE,
    DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.VLM,  # ✅ 改为 VLM
    DocumentType.INVOICE: ProcessingLayer.RULE,
    DocumentType.PURCHASE_CONTRACT: ProcessingLayer.VLM,     # ✅ 改为 VLM
    DocumentType.STOCK_CONTRACT: ProcessingLayer.VLM,        # ✅ 改为 VLM
    DocumentType.FUND_SUPERVISION: ProcessingLayer.RULE,
    DocumentType.DIVORCE_CERTIFICATE: ProcessingLayer.VLM,
    DocumentType.DIVORCE_AGREEMENT: ProcessingLayer.RULE,
    DocumentType.UNKNOWN: ProcessingLayer.VLM,               # ✅ 增强：类型识别 + 提取
}
```

---

## 三、代码修改清单

### 3.1 需要删除的文件/代码

| 文件 | 删除内容 | 原因 |
|------|---------|------|
| `vlm_classifier.py` | 整个文件 | VLM 分类兜底已移除 |
| `llm_layer.py` | 整个文件 | LLM 层已移除 |
| `service.py` | `run_ocr_tiered` 方法 | 分层 OCR 策略已移除 |
| `service.py` | VLM 分类器相关代码 | VLM 分类兜底已移除 |
| `service.py` | LLM 层初始化代码 | LLM 层已移除 |
| `pipeline.py` | LLM 层相关代码 | LLM 层已移除 |
| `config.py` | `ClassificationServiceConfig` | 不再需要 VLM 分类配置 |
| `config.py` | `LLMServiceConfig` | 不再需要 LLM 配置 |

### 3.2 需要修改的文件/代码

| 文件 | 修改内容 | 说明 |
|------|---------|------|
| `service.py` | 简化 `__init__` 方法 | 移除 VLM 分类器和 LLM 层初始化 |
| `service.py` | 简化 `run_ocr` 方法 | 只保留 PP-OCRv6 |
| `pipeline.py` | 修改 `DEFAULT_LAYER_ROUTING` | 合同类文档路由到 VLM 层 |
| `pipeline.py` | 简化 `process` 方法 | 移除 LLM 层相关逻辑 |
| `vlm_layer.py` | 增加多页提取能力 | 实现 `extract_multi_page` 方法 |
| `vlm_layer.py` | 增加类型识别能力 | 实现 UNKNOWN 文档的类型识别 + 提取 |
| `vlm_layer.py` | 增加合同类文档 Prompt | 添加购房合同、存量房合同、房产证的 Prompt |
| `config.py` | 简化配置 | 移除不需要的配置项 |

### 3.3 需要新增的代码

| 文件 | 新增内容 | 说明 |
|------|---------|------|
| `vlm_layer.py` | `extract_multi_page` 方法 | 多页文档提取 |
| `vlm_layer.py` | `UNKNOWN_EXTRACTION_PROMPT` | UNKNOWN 文档的类型识别 + 提取 Prompt |
| `vlm_layer.py` | `PURCHASE_CONTRACT_EXTRACTION_PROMPT` | 购房合同提取 Prompt |
| `vlm_layer.py` | `STOCK_CONTRACT_EXTRACTION_PROMPT` | 存量房合同提取 Prompt |
| `vlm_layer.py` | `PROPERTY_CERTIFICATE_EXTRACTION_PROMPT` | 房产证提取 Prompt |

---

## 四、实施步骤

### 阶段 1：架构简化（预计 2-3 小时）

1. **删除冗余代码**
   - 删除 `vlm_classifier.py`
   - 删除 `llm_layer.py`
   - 删除 `service.py` 中的 VLM 分类器和 LLM 层相关代码
   - 删除 `pipeline.py` 中的 LLM 层相关代码

2. **简化配置**
   - 移除 `ClassificationServiceConfig`
   - 移除 `LLMServiceConfig`
   - 简化 `OCRConfig`

3. **更新文档路由**
   - 修改 `pipeline.py` 中的 `DEFAULT_LAYER_ROUTING`
   - 将合同类文档路由到 VLM 层

### 阶段 2：VLM 层增强（预计 3-4 小时）

1. **实现多页提取**
   - 在 `vlm_layer.py` 中实现 `extract_multi_page` 方法
   - 实现字段合并逻辑

2. **实现类型识别 + 提取**
   - 设计 UNKNOWN 文档的 Prompt
   - 实现类型识别和字段提取的组合逻辑

3. **添加合同类文档 Prompt**
   - 购房合同 Prompt
   - 存量房合同 Prompt
   - 房产证 Prompt

4. **更新 Pipeline 逻辑**
   - 修改 `pipeline.py` 中的 `process` 方法
   - 支持多页文档处理

### 阶段 3：测试验证（预计 2-3 小时）

1. **单元测试**
   - 测试 VLM 层的类型识别功能
   - 测试多页提取功能
   - 测试字段合并逻辑

2. **集成测试**
   - 使用定向评测脚本测试
   - 对比优化前后的性能

3. **性能评测**
   - 处理速度对比
   - 提取准确率对比
   - 字段完整性对比

---

## 五、预期效果

### 5.1 性能提升

| 指标 | v1.0（当前） | v2.0（目标） | 提升 |
|------|------------|------------|------|
| **组件数量** | 5 个 | 3 个 | -40% |
| **决策点** | 4 个 | 2 个 | -50% |
| **处理速度** | 114.5s/张 | ~90s/张 | +20% |
| **合同提取成功率** | 0% | 70%+ | +70% |
| **维护成本** | 高 | 低 | -50% |

### 5.2 功能改进

1. **合同类文档提取**
   - v1.0：LLM 层失败，0 字段
   - v2.0：VLM 层多页提取，预期 4-5 字段

2. **UNKNOWN 文档处理**
   - v1.0：VLM 分类（20-30s）+ VLM 提取（40-60s）= 60-90s
   - v2.0：VLM 类型识别 + 提取（40-60s），节省 20-30s

3. **架构清晰度**
   - v1.0：5 个组件，4 个决策点，复杂
   - v2.0：3 个组件，2 个决策点，简洁

---

## 六、风险与应对

### 6.1 风险 1：VLM 类型识别准确率

**风险描述**：
- VLM 同时做类型识别和字段提取，可能准确率下降

**应对措施**：
- 设计高质量的 Prompt，明确要求类型识别和字段提取
- 在 Prompt 中提供文档类型列表和字段列表
- 测试验证准确率，必要时调整 Prompt

### 6.2 风险 2：多页提取耗时

**风险描述**：
- 多页文档需要逐页提取，可能耗时较长

**应对措施**：
- 限制处理页数（如前 15 页）
- 优化 VLM 调用速度
- 必要时可以并行处理多页（需要评估 API 并发限制）

### 6.3 风险 3：字段合并逻辑

**风险描述**：
- 多页提取后字段合并可能出错（如重复字段、冲突字段）

**应对措施**：
- 使用"取第一个非空值"策略
- 添加日志记录每页提取的字段
- 必要时可以人工审核合并结果

---

## 七、相关文档

- [架构简化方案深度分析](./architecture_simplification_analysis.md)
- [多页 VLM 提取方案](./multi_page_vlm_extraction_plan.md)
- [关键技术讨论记录](./technical_discussion_llm_layer_analysis.md)
- [架构流程说明](./architecture_flow.md)

---

## 八、附录

### 8.1 术语表

| 术语 | 说明 |
|------|------|
| PP-OCRv6 | PaddlePaddle 的 OCR 引擎，版本 6 |
| PaddleOCR-VL | PaddleOCR 的视觉语言模型版本 |
| VLM | Vision-Language Model，视觉语言模型 |
| LLM | Large Language Model，大语言模型 |
| PP-ChatOCRv4 | PaddlePaddle 的文档理解框架 |
| Qwen2.5-VL-7B | 阿里云的视觉语言模型 |
| Qwen35-4B | 阿里云的文本语言模型 |

### 8.2 参考资料

- [PaddleOCR 官方文档](https://github.com/PaddlePaddle/PaddleOCR)
- [Qwen2.5-VL 官方文档](https://github.com/QwenLM/Qwen-VL)
- [PP-ChatOCRv4 论文](https://arxiv.org/abs/2403.12350)
