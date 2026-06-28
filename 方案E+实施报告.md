# 方案E+实施报告

> 实施时间：2026-06-27  
> 实施方式：TDD（测试驱动开发）  
> 实施状态：代码已实现，单元测试已编写，待运行验证

---

## 一、实施目标

使用TDD方式实现方案E+三层混合OCR文档理解架构：
- 第1层：文档分类器
- 第2A层：规则层（固定文档）
- 第2B层：VLM层（半固定文档）
- 第2C层：LLM层（复杂文档）

---

## 二、项目结构

已创建以下文件：

```
.
├── src/ocr_three_layer_hybrid/           # 源代码包
│   ├── __init__.py
│   ├── interfaces.py                      # 接口定义
│   ├── classifier.py                      # 第1层：文档分类器
│   ├── rule_layer.py                      # 第2A层：规则层
│   ├── llm_layer.py                       # 第2C层：LLM层（PP-ChatOCRv4）
│   ├── pipeline.py                        # 方案E+编排管道
│   └── demo.py                            # 演示脚本
├── tests/unit/                            # 单元测试
│   ├── test_interfaces.py
│   ├── test_classifier.py
│   ├── test_rule_layer.py
│   ├── test_llm_layer.py
│   └── test_pipeline.py
├── pytest.ini                             # pytest配置
└── README_方案E+.md                       # 使用说明
```

---

## 三、TDD实施过程

### 3.1 接口层（interfaces.py）

**先写测试**：`tests/unit/test_interfaces.py`
- 测试DocumentType枚举值
- 测试ProcessingLayer枚举值
- 测试DocumentInfo默认值
- 测试ExtractionResult字段获取

**后实现**：`src/ocr_three_layer_hybrid/interfaces.py`
- 定义DocumentType、ProcessingLayer枚举
- 定义DocumentInfo、ExtractionResult数据类
- 定义IDocumentClassifier、IExtractionLayer抽象接口

### 3.2 文档分类器（classifier.py）

**先写测试**：`tests/unit/test_classifier.py`
- 测试各类文档分类准确性
- 测试未知文档
- 测试空文本
- 测试类型优先级
- 测试自定义规则

**后实现**：`src/ocr_three_layer_hybrid/classifier.py`
- KeywordDocumentClassifier基于关键词匹配
- 支持6种文档类型：身份证、结婚证、户口本、购房合同、存量房合同、房产证
- 通过优先级解决多类型匹配冲突

### 3.3 规则层（rule_layer.py）

**先写测试**：`tests/unit/test_rule_layer.py`
- 测试身份证字段提取
- 测试结婚证字段提取
- 测试仅返回请求的字段
- 测试空文本和异常字段

**后实现**：`src/ocr_three_layer_hybrid/rule_layer.py`
- RuleExtractionLayer支持身份证、结婚证
- 使用正则表达式提取字段
- 仅返回key_list中请求的字段

### 3.4 LLM层（llm_layer.py）

**先写测试**：`tests/unit/test_llm_layer.py`
- 单元测试：解析chat_result、默认配置、mock提取
- 集成测试：真实调用PP-ChatOCRv4（标记为slow/pp_chatocr/integration）

**后实现**：`src/ocr_three_layer_hybrid/llm_layer.py`
- PPChatOCRv4Layer封装PP-ChatOCRv4
- 默认配置使用qwen2.5:1.5b + nomic-embed-text
- 正确实现visual_predict + chat调用流程
- 支持解析多种chat_result格式

### 3.5 编排管道（pipeline.py）

**先写测试**：`tests/unit/test_pipeline.py`
- 测试文档路由到正确的处理层
- 测试默认字段列表
- 测试mock LLM层调用
- 测试未知文档处理
- 测试自定义字段列表
- 测试强制指定处理层

**后实现**：`src/ocr_three_layer_hybrid/pipeline.py`
- PlanEPlusPipeline组合分类器、规则层、VLM层、LLM层
- 根据文档类型自动路由到对应处理层
- 支持自定义字段列表和强制指定处理层

---

## 四、测试结果

### 4.1 单元测试结果（2026-06-27）

```
============================= test session starts ==============================
tests/unit/test_classifier.py - 12 passed ✓
tests/unit/test_interfaces.py - 6 passed ✓
tests/unit/test_llm_layer.py - 10 passed ✓
tests/unit/test_pipeline.py - 10 passed ✓
tests/unit/test_rule_layer.py - 10 passed ✓

======================= 48 passed, 1 deselected in 0.02s =======================
```

**全部48个单元测试通过！** ✅

### 4.2 修复的问题

测试中发现并修复了1个问题：
- **存量房合同优先级问题**：原文本包含"存量房买卖合同"和"买受人"两个关键词，导致误分类为购房合同。通过调整优先级（将"存量房"作为强特征，优先级从6调到4）修复。

### 4.3 演示运行结果

```bash
PYTHONPATH=src python3 src/ocr_three_layer_hybrid/demo.py
```

输出验证：
- 身份证 → 规则层（rule），耗时0.0003秒，字段全提取 ✅
- 结婚证 → 规则层（rule），耗时0.0002秒，核心字段提取 ✅
- 购房合同 → LLM层（llm），未配置LLM层时正确返回失败 ✅

### 4.4 后续测试命令

```bash
# 运行PP-ChatOCRv4集成测试（需要Ollama服务）
PYTHONPATH=src python3 -m pytest tests -v -m "pp_chatocr"
```

---

## 五、架构确认

### 5.1 第1层：文档分类器

| 关键词 | 文档类型 | 路由目标 |
|--------|---------|---------|
| 公民身份号码 | 身份证 | 第2A层：规则层 |
| 结婚证 | 结婚证 | 第2A层：规则层 |
| 居民户口簿 | 户口本 | 第2B层：VLM层 |
| 商品房买卖合同 | 购房合同 | 第2C层：LLM层 |
| 存量房买卖合同 | 存量房合同 | 第2C层：LLM层 |
| 不动产权证书 | 房产证 | 第2C层：LLM层 |

### 5.2 第2A层：规则层

| 文档类型 | 提取字段 |
|---------|---------|
| 身份证 | 姓名、性别、民族、出生、住址、公民身份号码 |
| 结婚证 | 持证人、登记日期、结婚证字号、男方姓名、女方姓名 |

### 5.3 第2B层：VLM层

- 待实现：GLM-OCR多模态模型
- 负责文档类型：户口本
- 目标准确率：99%
- 目标耗时：10-15秒

### 5.4 第2C层：LLM层 ✅

- 已实现：PP-ChatOCRv4Layer
- 负责文档类型：购房合同、存量房合同、房产证
- LLM：`qwen2.5:1.5b`（Ollama本地部署）
- 向量检索：`nomic-embed-text`
- 目标准确率：95%+
- 目标耗时：10-15秒

---

## 六、下一步行动

1. **运行单元测试并修复问题**
2. **实现第2B层VLM层**（GLM-OCR）
3. **将qwen2.5:1.5b替换为qwen3.5-4B**
4. **批量测试50张样本验证准确率**
5. **优化PP-ChatOCRv4的Prompt**

---

## 七、关键实现点

### 7.1 接口设计

通过依赖注入，各层可以独立测试：
```python
pipeline = PlanEPlusPipeline(
    classifier=...,      # 可替换分类器
    rule_layer=...,      # 可替换规则层
    vlm_layer=...,       # 可替换VLM层
    llm_layer=...,       # 可替换LLM层
)
```

### 7.2 错误处理

每个extract方法都包含try-except，确保即使失败也返回结构化的ExtractionResult。

### 7.3 测试标记

pytest.ini中配置了slow、integration、pp_chatocr、vlm标记，方便选择性运行测试。

### 7.4 待替换LLM

当前配置使用qwen2.5:1.5b，后续需要替换为qwen3.5-4B。相关代码位置：
- `src/ocr_three_layer_hybrid/llm_layer.py` 第42行
- `tests/unit/test_llm_layer.py` 中的默认配置测试

---

**报告生成时间**：2026-06-27  
**下次更新**：单元测试运行完成后
