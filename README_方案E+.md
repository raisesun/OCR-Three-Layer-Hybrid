# 方案E+：三层混合OCR文档理解架构

## 架构概览

```
第1层：文档分类器（DocumentClassifier）
    ↓
第2层：字段提取层
    ├── 第2A层：规则层（Rule Layer）→ 身份证、结婚证
    ├── 第2B层：VLM层（VLM Layer）→ 户口本
    └── 第2C层：LLM层（LLM Layer）→ 购房合同、房产证
```

## 项目结构

```
.
├── src/ocr_three_layer_hybrid/      # 源代码
│   ├── __init__.py
│   ├── interfaces.py                # 接口和核心数据结构
│   ├── classifier.py                # 第1层：文档分类器
│   ├── rule_layer.py                # 第2A层：规则层
│   ├── llm_layer.py                 # 第2C层：LLM层
│   ├── pipeline.py                  # 方案E+编排管道
│   └── demo.py                      # 演示脚本
├── tests/                           # 测试
│   ├── unit/                        # 单元测试
│   │   ├── test_interfaces.py
│   │   ├── test_classifier.py
│   │   ├── test_rule_layer.py
│   │   ├── test_llm_layer.py
│   │   └── test_pipeline.py
│   ├── integration/                 # 集成测试
│   └── fixtures/                    # 测试数据
├── pytest.ini                       # pytest配置
└── README_方案E+.md                 # 本文件
```

## 运行测试

```bash
# 运行所有单元测试（不包含慢速/集成测试）
PYTHONPATH=src python3 -m pytest tests/unit -v -m "not slow and not integration and not pp_chatocr and not vlm"

# 运行所有测试
PYTHONPATH=src python3 -m pytest tests -v

# 运行PP-ChatOCRv4集成测试（需要Ollama服务）
PYTHONPATH=src python3 -m pytest tests -v -m "pp_chatocr"
```

## 使用示例

### 基础用法

```python
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.llm_layer import PPChatOCRv4Layer

# 初始化完整管道
llm_layer = PPChatOCRv4Layer(
    chat_bot_config={
        "api_type": "openai",
        "model_name": "qwen2.5:1.5b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    },
    retriever_config={
        "api_type": "openai",
        "model_name": "nomic-embed-text",
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
    },
)

pipeline = PlanEPlusPipeline(llm_layer=llm_layer)

# 处理文档
result = pipeline.process(
    image_path="/path/to/document.jpg",
    ocr_texts=["商品房买卖合同", "买受人 张三", "出卖人 李四"],
)

print(f"文档类型：{result.doc_type}")
print(f"处理层：{result.layer}")
print(f"提取字段：{result.fields}")
```

### 使用模拟数据演示

```bash
PYTHONPATH=src python3 src/ocr_three_layer_hybrid/demo.py
```

### 使用真实图片演示（需要Ollama）

```bash
PYTHONPATH=src python3 src/ocr_three_layer_hybrid/demo.py --real
```

## 待办事项

- [ ] 替换LLM：将qwen2.5:1.5b替换为qwen3.5-4B
- [ ] 实现第2B层VLM层（GLM-OCR）
- [ ] 批量测试50张样本验证准确率
- [ ] 优化PP-ChatOCRv4的Prompt
- [ ] 添加OCR文本提取适配器（统一PaddleOCR版本差异）
