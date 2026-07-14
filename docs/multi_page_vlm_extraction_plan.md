# 多页文档 VLM 提取优化方案

> **⚠️ 注意（2026-07-09）**：本文档中涉及的 `ProcessingLayer.LLM` 已彻底移除。当前架构（v2.1.0）仅保留 `ProcessingLayer.RULE` + `ProcessingLayer.VLM` 两种处理层。LLM 层（PP-ChatOCRv4）在处理购房合同、存量房合同、房产证时完全失败，已于 v2.0 移除。本文档作为历史参考保留，其中关于 LLM 层失败的分析和 VLM 替代方案的方向仍然有效。

## 背景

**当前问题**：
- 节点3.3 LLM层（PP-ChatOCRv4 + Qwen35-4B）处理购房合同、存量房合同、房产证时完全失败
- 提取字段数为 0，耗时异常长（197-316秒/文档）
- 需要寻找替代方案

**优化思路**：
使用节点3.2 VLM层（Qwen2.5-VL-7B）直接处理多页合同文档，替代失败的 LLM 层。

## 方案核心

### 1. 文档特征分析

**多页文档特点**：
- 购房合同：5-50+ 页
- 存量房合同：5-30+ 页
- 房产证：3-10+ 页

**字段分布特征**：
- 字段分散在多页，不集中在单页
- 每页可能包含 0 个、1 个或多个目标字段
- 不同页面的字段类型不同

**示例**（购房合同 5 页）：
```
页1: 买受人=张三, 地址=合肥市..., 总价款=空, 建筑面积=空, 签订日期=空
页2: 买受人=空, 地址=空, 总价款=100万, 建筑面积=90㎡, 签订日期=空
页3: 买受人=空, 地址=空, 总价款=空, 建筑面积=空, 签订日期=2024-01-01
页4: 全空
页5: 全空
```

### 2. 处理流程

```
多页文档（N张图片）
  ↓
[步骤1] 确定目标字段列表
  - 购房合同: 合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积
  - 存量房合同: 合同编号、买受人、出卖人、总价款、签订日期、房屋地址、建筑面积
  - 房产证: 证书号、权利人、共有情况、不动产单元号、房屋地址、建筑面积、用途
  ↓
[步骤2] 逐页 VLM 提取（固定字段列表）
  for page in pages[:max_pages]:  # 限制处理页数（如15页）
    fields = vlm_extract(page, key_list)
    # VLM Prompt: "请从图片中提取以下字段：合同编号、买受人、出卖人...，不存在的返回空字符串"
  ↓
[步骤3] 字段合并（取第一个非空值）
  merged_fields = {}
  for page_fields in all_pages_fields:
    for key, value in page_fields.items():
      if value and key not in merged_fields:
        merged_fields[key] = value
  ↓
[步骤4] 返回合并结果
  return merged_fields
```

### 3. 技术实现

#### 3.1 修改文档路由（pipeline.py）

```python
DEFAULT_LAYER_ROUTING = {
    # 修改前
    DocumentType.PURCHASE_CONTRACT: ProcessingLayer.LLM,      # ❌ 失败
    DocumentType.STOCK_CONTRACT: ProcessingLayer.LLM,         # ❌ 失败
    DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.LLM,   # ❌ 可能失败
    
    # 修改后
    DocumentType.PURCHASE_CONTRACT: ProcessingLayer.VLM,      # ✅ 使用 VLM
    DocumentType.STOCK_CONTRACT: ProcessingLayer.VLM,         # ✅ 使用 VLM
    DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.VLM,   # ✅ 使用 VLM
}
```

#### 3.2 增强 VLM 层多页处理（vlm_layer.py）

```python
def extract_multi_page(
    self, 
    image_paths: List[str], 
    key_list: List[str],
    max_pages: int = 15
) -> ExtractionResult:
    """
    多页文档提取：逐页提取 + 字段合并
    
    Args:
        image_paths: 图片路径列表
        key_list: 目标字段列表
        max_pages: 最大处理页数（性能优化）
    
    Returns:
        合并后的提取结果
    """
    merged_fields = {k: "" for k in key_list}
    total_time = 0.0
    pages_processed = 0
    
    for img_path in image_paths[:max_pages]:
        # 构建文档信息
        doc_info = DocumentInfo(
            doc_type=self._detect_doc_type(img_path),
            image_path=img_path,
            ocr_texts=[],
            confidence=1.0,
        )
        
        # 单页提取
        result = self.extract(doc_info, key_list)
        total_time += result.time_cost
        pages_processed += 1
        
        # 合并字段（取第一个非空值）
        for key, value in result.fields.items():
            if value and not merged_fields.get(key):
                merged_fields[key] = value
    
    return ExtractionResult(
        doc_type=doc_info.doc_type,
        layer=ProcessingLayer.VLM,
        fields=merged_fields,
        success=len([v for v in merged_fields.values() if v]) > 0,
        time_cost=total_time,
    )
```

#### 3.3 优化 VLM Prompt（vlm_layer.py）

```python
PROMPT_TEMPLATES = {
    DocumentType.PURCHASE_CONTRACT: (
        "你是一名专业的购房合同信息提取专家。请仔细识别图片中的合同内容，"
        "按以下JSON格式输出所有可识别的字段信息。\n\n"
        "## 输出JSON格式（必须严格使用以下键名）\n"
        "{\n"
        '  "合同编号": "",\n'
        '  "买受人": "",\n'
        '  "出卖人": "",\n'
        '  "总价款": "",\n'
        '  "签订日期": "",\n'
        '  "房屋地址": "",\n'
        '  "建筑面积": ""\n'
        "}\n\n"
        "## 重要注意事项\n"
        "- 只输出纯JSON，不要包含markdown代码块标记\n"
        "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
        "- 不要输出任何其他解释文字\n"
        "- 仔细检查图片中的每个字段，确保不遗漏\n"
    ),
    DocumentType.STOCK_CONTRACT: (
        "你是一名专业的存量房买卖合同信息提取专家。请仔细识别图片中的合同内容，"
        "按以下JSON格式输出所有可识别的字段信息。\n\n"
        "## 输出JSON格式（必须严格使用以下键名）\n"
        "{\n"
        '  "合同编号": "",\n'
        '  "买受人": "",\n'
        '  "出卖人": "",\n'
        '  "总价款": "",\n'
        '  "签订日期": "",\n'
        '  "房屋地址": "",\n'
        '  "建筑面积": ""\n'
        "}\n\n"
        "## 重要注意事项\n"
        "- 只输出纯JSON，不要包含markdown代码块标记\n"
        "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
        "- 不要输出任何其他解释文字\n"
    ),
    DocumentType.PROPERTY_CERTIFICATE: (
        "你是一名专业的不动产权证书信息提取专家。请仔细识别图片中的证书内容，"
        "按以下JSON格式输出所有可识别的字段信息。\n\n"
        "## 输出JSON格式（必须严格使用以下键名）\n"
        "{\n"
        '  "证书号": "",\n'
        '  "权利人": "",\n'
        '  "共有情况": "",\n'
        '  "不动产单元号": "",\n'
        '  "房屋地址": "",\n'
        '  "建筑面积": "",\n'
        '  "用途": ""\n'
        "}\n\n"
        "## 重要注意事项\n"
        "- 只输出纯JSON，不要包含markdown代码块标记\n"
        "- 如果某个字段在图片中不存在或无法识别，该字段值保留为空字符串\n"
        "- 不要输出任何其他解释文字\n"
    ),
}
```

#### 3.4 服务层多页处理（service.py）

```python
def process_multi_page(
    self, 
    image_paths: List[str], 
    key_list: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    处理多页文档（购房合同、存量房合同、房产证）
    
    Args:
        image_paths: 图片路径列表
        key_list: 目标字段列表（可选，不传则使用默认）
    
    Returns:
        处理结果
    """
    # 1. 分类（使用第一页判断文档类型）
    first_page = image_paths[0]
    ocr_text = self.run_ocr(first_page)
    doc_info = self._classifier.classify(first_page, [ocr_text])
    
    # 2. 获取默认字段列表
    if key_list is None:
        key_list = self._pipeline.key_lists.get(doc_info.doc_type, [])
    
    # 3. 多页提取
    if doc_info.doc_type in [
        DocumentType.PURCHASE_CONTRACT,
        DocumentType.STOCK_CONTRACT,
        DocumentType.PROPERTY_CERTIFICATE,
    ]:
        result = self._pipeline.vlm_layer.extract_multi_page(
            image_paths, key_list, max_pages=15
        )
    else:
        # 单页文档
        result = self._pipeline.process(first_page, [ocr_text], doc_info=doc_info)
    
    # 4. 构建返回结果
    return {
        "classification": self._build_classification_dict(doc_info),
        "extraction": {
            "success": result.success,
            "layer": result.layer.value,
            "fields": result.fields,
            "pages_processed": len(image_paths),
        },
        "image_paths": image_paths,
    }
```

## 性能预期

### 处理速度

| 文档类型 | 页数 | VLM单页耗时 | 总耗时（预期） |
|---------|------|------------|--------------|
| 购房合同 | 5页 | 10-20秒 | 50-100秒 |
| 存量房合同 | 5页 | 10-20秒 | 50-100秒 |
| 房产证 | 3页 | 10-20秒 | 30-60秒 |

**对比当前 LLM 层**：
- LLM 层：197-316 秒/文档（且 0 字段）
- VLM 层：50-100 秒/文档（预期 70%+ 成功率）

**速度提升**：2-3 倍

### 提取成功率

**参考 VLM 层在其他文档上的表现**：
- 身份证：100% 成功率，平均 3.5 字段
- 结婚证：100% 成功率，平均 7.0 字段
- 户口本：100% 成功率，平均 2.5 字段
- 发票：100% 成功率，平均 6.0 字段

**预期合同类文档**：
- 购房合同：70%+ 成功率，平均 4-5 字段
- 存量房合同：70%+ 成功率，平均 4-5 字段
- 房产证：80%+ 成功率，平均 5-6 字段

## 优势总结

1. ✅ **架构简化**：统一使用 VLM 层，无需维护 LLM 层
2. ✅ **速度提升**：2-3 倍性能提升
3. ✅ **成功率提升**：从 0% → 70%+
4. ✅ **可扩展性**：易于添加新文档类型和字段
5. ✅ **故障点减少**：去掉复杂的 PP-ChatOCRv4 框架
6. ✅ **多页处理自然**：逐页提取 + 字段合并，符合文档特征

## 实施步骤

1. **阶段1**：修改文档路由，将合同类文档路由到 VLM 层
2. **阶段2**：增强 VLM 层多页处理能力
3. **阶段3**：优化合同类文档的 VLM Prompt
4. **阶段4**：测试验证（使用定向评测脚本）
5. **阶段5**：性能调优（限制处理页数、并行处理等）

## 风险与应对

**风险1**：VLM 对复杂合同的理解能力不足
- **应对**：优化 Prompt，提供更详细的字段说明和示例

**风险2**：多页处理耗时过长
- **应对**：限制处理页数（如前 15 页），或只处理包含关键字段的页面

**风险3**：字段合并逻辑错误
- **应对**：使用"取第一个非空值"策略，避免覆盖

## 测试验证

使用现有的定向评测脚本 `scripts/vlm_evaluation_targeted.py`：
- 测试存量房业务分类（BBJZ-2025-1013085）
- 测试增量房业务分类（202402190050）
- 对比修改前后的成功率和字段数

## 结论

**推荐方案**：使用 VLM 层替代 LLM 层处理多页合同文档

**理由**：
1. LLM 层当前完全失败，需要重新设计
2. VLM 层在其他文档上表现良好
3. 多页 VLM 提取方案符合文档特征
4. 预期性能提升 2-3 倍，成功率从 0% → 70%+

**下一步**：实施该方案并进行测试验证
