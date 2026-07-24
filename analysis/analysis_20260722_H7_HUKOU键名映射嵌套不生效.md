# H7 深度分析：HUKOU_KEY_MAPPINGS 在 UNKNOWN 嵌套格式路径下不生效

- **分析日期**：2026-07-22
- **问题编号**：H7（审查报告 `docs/reviews/code_review_20260722.md`，🟠高）
- **状态**：未修复

---

## 1. 问题本质（一句话）

`_parse_json_response` 处理 UNKNOWN 文档的嵌套格式 `{"doc_type": "...", "fields": {...}}` 时，**直接复制 `fields` 键值并提前 return**，跳过了 `HUKOU_KEY_MAPPINGS` 键名映射。当 UNKNOWN 文档实为户口本、VLM 返回的键名（如"户主姓名"）与 `key_list` 期望的字段名（如"户主"）不一致时，**字段无法映射，值丢失**。

---

## 2. 事实链（代码层面，已逐行验证）

### 2.1 HUKOU_KEY_MAPPINGS（vlm_layer.py:342-351）
```python
HUKOU_KEY_MAPPINGS: Dict[str, List[str]] = {
    "姓名": ["姓名", "名字"],
    "户主": ["户主", "户主姓名"],          # target_key="户主" <- possible_keys=["户主","户主姓名"]
    "与户主关系": ["与户主关系", "户主或与户主关系", "关系"],
    "性别": ["性别", "性 别"],
    "出生日期": ["出生日期", "生日"],
    "民族": ["民族", "民 族"],
    "户籍地址": ["户籍地址", "住址", "住 址", "地址"],
    "公民身份号码": ["公民身份号码", "身份证号", "身份证号码", "公民身份证件编号"],
}
```
- key = `target_key`（key_list 期望的字段名，如"户主"）
- value = `possible_keys`（VLM 可能输出的键名，如"户主"或"户主姓名"）

### 2.2 _parse_json_response 嵌套路径（:384-391）
```python
# 处理UNKNOWN文档的嵌套格式：{"doc_type": "...", "fields": {...}}
if "fields" in parsed and isinstance(parsed["fields"], dict):
    nested_fields = parsed["fields"]
    for key, value in nested_fields.items():
        if value and str(value).strip():
            fields[key] = str(value)       # ← 直接用 VLM 的键名
    return fields                           # ← 提前 return，跳过 HUKOU_KEY_MAPPINGS

# 非嵌套路径：使用键名映射（HUKOU_KEY_MAPPINGS）
for target_key in key_list:
    if target_key in self.HUKOU_KEY_MAPPINGS:
        for possible_key in self.HUKOU_KEY_MAPPINGS[target_key]:
            if possible_key in parsed:
                fields[target_key] = str(parsed[possible_key])
                break
    elif target_key in parsed:
        fields[target_key] = str(parsed[target_key])
```

### 2.3 H7 触发场景
UNKNOWN 文档（实为户口本），VLM 返回：
```json
{"doc_type": "户口本", "fields": {"户主姓名": "张三", "户号": "12345"}}
```
- 嵌套路径：`nested_fields = {"户主姓名": "张三", "户号": "12345"}`
- `fields["户主姓名"] = "张三"`, `fields["户号"] = "12345"`
- return（跳过 HUKOU_KEY_MAPPINGS）
- 但 `key_list` 期望 `["户主", ...]`（target_key="户主"）
- `fields["户主"] = ""`（空，因为 fields 有"户主姓名"但 key_list 取"户主"）
- **"户主姓名"->"户主" 的映射未执行，值丢失**

### 2.4 非嵌套路径（正确）
若 VLM 返回扁平 `{"户主姓名": "张三"}`：
- 走 HUKOU_KEY_MAPPINGS：target_key="户主"，possible_keys=["户主","户主姓名"]
- "户主姓名" in parsed -> `fields["户主"] = "张三"` ✅ 正确

---

## 3. 根因分析

### 3.1 为什么嵌套路径跳过映射？
- 嵌套格式 `{"fields": {...}}` 是 UNKNOWN 文档的特殊格式（VLM 同时返回 doc_type + fields）
- 嵌套路径设计为"直接使用所有字段"（line 386 注释："UNKNOWN文档：VLM返回嵌套格式，直接使用所有字段"）
- 但"直接使用"假设 VLM 的键名 == key_list 的字段名。若不一致（如"户主姓名" vs "户主"），丢失

### 3.2 苏格拉底追问
- **Q：为什么不映射？**
  -> 嵌套路径提前 return，没走 HUKOU_KEY_MAPPINGS 逻辑。设计遗漏。
- **Q：VLM 嵌套格式返回的键名是什么？**
  -> 取决于 VLM prompt。UNKNOWN prompt 让 VLM 自由返回字段名，可能用"户主姓名"或"户主"。需运行时确认。
- **Q：影响范围？**
  -> 仅 UNKNOWN 文档走 VLM 提取 + VLM 返回嵌套格式 + 键名不匹配 key_list。多条件触发。
- **Q：是 bug 还是设计？**
  -> 设计遗漏。嵌套路径应复用 HUKOU_KEY_MAPPINGS。

---

## 4. 批判性评估：严重性

agent 标 🟠高，**需分情况**：
- **触发条件**：UNKNOWN 文档 + VLM 返回嵌套 `{"fields":{}}` + VLM 键名 ≠ key_list 字段名
- **实际概率**：
  - UNKNOWN 文档走 VLM：常见（分类不确定时）
  - VLM 返回嵌套格式：取决于 prompt（UNKNOWN prompt 可能要求嵌套）
  - 键名不匹配：VLM 可能用"户主姓名"或"户主"，需运行时确认
- **影响**：字段值丢失（在 fields 但键名不对，key_list 取不到）-> 触发 VLM 兜底或返回空

**真实严重性**：🟡中（多条件触发，需 VLM 返回特定格式）。但有 VLM 兜底保底（不丢数据，性能损失）。

**需运行时确认**：VLM 对 UNKNOWN 户口本返回的 fields 键名格式。

---

## 5. 修复对整体系统的影响

### 5.1 正面影响
1. **避免字段丢失**：UNKNOWN 户口本 VLM 提取的字段正确映射到 key_list
2. **提升提取准确率**：减少因键名不匹配导致的空字段 + VLM 兜底

### 5.2 潜在风险
1. **改 VLM 解析逻辑**：`_parse_json_response` 是 VLM 响应解析核心
2. **映射方向**：嵌套路径需反向映射（VLM 键 -> target_key），与非嵌套（target_key -> possible_keys）方向不同，需仔细实现
3. **键名冲突**：若 VLM 键同时匹配多个 target_key 的 possible_keys，需明确优先级
4. **测试**：`test_vlm_layer.py` 需回归 + 加嵌套格式映射测试
5. **VLM 服务依赖**：真实 VLM 测试需 VLM 服务

### 5.3 影响范围
- **功能正确性**：UNKNOWN 户口本字段提取正确（若触发）
- **测试**：回归 `test_vlm_layer.py`
- **部署**：无影响

---

## 6. 修复方案

### 方案 A：嵌套路径也应用 HUKOU_KEY_MAPPINGS（推荐）
```python
if "fields" in parsed and isinstance(parsed["fields"], dict):
    nested_fields = parsed["fields"]
    # 先尝试 HUKOU_KEY_MAPPINGS 映射（VLM 键 -> target_key）
    for target_key in key_list:
        if target_key in self.HUKOU_KEY_MAPPINGS:
            for possible_key in self.HUKOU_KEY_MAPPINGS[target_key]:
                if possible_key in nested_fields and nested_fields[possible_key]:
                    fields[target_key] = str(nested_fields[possible_key])
                    break
        elif target_key in nested_fields:
            fields[target_key] = str(nested_fields[target_key])
    # 兜底：未映射的 nested_fields 键直接放入（保留 VLM 原始键，防漏）
    for key, value in nested_fields.items():
        if value and str(value).strip() and key not in fields:
            fields[key] = str(value)
    return fields
```
- 优点：嵌套路径复用 HUKOU_KEY_MAPPINGS，键名正确映射
- 缺点：需确保映射方向正确（target_key -> possible_keys，查 nested_fields）

### 方案 B：提取映射逻辑为公共方法
```python
def _apply_key_mappings(self, fields, source_dict, key_list):
    """应用 HUKOU_KEY_MAPPINGS，从 source_dict 提取到 fields"""
    for target_key in key_list:
        if target_key in self.HUKOU_KEY_MAPPINGS:
            for possible_key in self.HUKOU_KEY_MAPPINGS[target_key]:
                if possible_key in source_dict and source_dict[possible_key]:
                    fields[target_key] = str(source_dict[possible_key])
                    break
        elif target_key in source_dict:
            fields[target_key] = str(source_dict[target_key])
    return fields
```
嵌套和非嵌套路径都调此方法。
- 优点：DRY、统一
- 缺点：需重构（提取方法 + 两处调用）

---

## 7. 推荐方案

**方案 A（嵌套路径应用 HUKOU_KEY_MAPPINGS）**，理由：
1. **根治**：嵌套路径复用映射，键名正确
2. **最小改动**：仅改嵌套分支
3. **兜底保留**：未映射的键直接放入（防漏）

**实施要点**：
- 嵌套分支：先按 HUKOU_KEY_MAPPINGS 映射 target_key，再兜底放未映射键
- 保留 `return fields`（嵌套路径仍提前返回，但映射后）

**需运行时确认**：VLM 对 UNKNOWN 户口本返回的 fields 键名（"户主"还是"户主姓名"）。需 VLM 服务。

---

## 8. 下一步行动

1. **（建议）运行时确认 VLM 嵌套格式键名**：启动 Qwen2.5-VL（默认 VLM），对 UNKNOWN 户口本跑 vlm_layer.extract，看返回的 fields 键名
2. 按方案 A 修复
3. 回归 `test_vlm_layer.py` + 加嵌套格式映射测试

**优先级**：H7 是中优先级（多条件触发 + VLM 兜底保底）。低于已修 17 项。建议有 VLM 环境时确认触发概率后修复。

**模型说明**：默认 VLM 是 Qwen2.5-VL-7B（port 8082），非 GLM-OCR。H6 验证用 GLM-OCR（8080）是因 Qwen 未启动。H7 验证应启动 Qwen 确认默认 VLM 行为。
