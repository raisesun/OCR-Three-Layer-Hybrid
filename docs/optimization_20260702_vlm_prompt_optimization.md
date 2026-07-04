# VLM提示词优化 - 实施总结

**日期**: 2026-07-02  
**目标**: 针对不同PageType优化VLM层提示词，提高提取准确率

## 1. VLM层提示词优化

### 1.1 离婚证 (Divorce Certificate)

| 页面类型 | DocumentType | 提示词策略 |
|---------|--------------|-----------|
| 内容页 | `DIVORCE_CERTIFICATE_CONTENT` | 提取所有13个字段（离婚证字号、登记日期、持证人、双方信息） |
| 封面页 | `DIVORCE_CERTIFICATE_COVER` | 返回空JSON `{}` |
| 盖章页 | `DIVORCE_CERTIFICATE_STAMP` | 返回空JSON `{}` |

### 1.2 结婚证 (Marriage Certificate)

| 页面类型 | DocumentType | 提示词策略 |
|---------|--------------|-----------|
| 内容页 | `MARRIAGE_CERTIFICATE_CONTENT` | 提取所有7个字段（结婚证字号、登记日期、持证人、双方信息） |
| 封面页 | `MARRIAGE_CERTIFICATE_COVER` | 返回空JSON `{}` |
| 盖章页 | `MARRIAGE_CERTIFICATE_STAMP` | 返回空JSON `{}` |

### 1.3 户口本 (Household Register)

| 页面类型 | DocumentType | 提示词策略 |
|---------|--------------|-----------|
| 首页 | `HOUSEHOLD_REGISTER_COVER` | 提取4个字段（户别、户主姓名、户号、住址） |
| 个人页 | `HOUSEHOLD_REGISTER_CONTENT` | 提取6个字段（姓名、与户主关系、性别、出生日期、民族、公民身份号码） |
| 索引页 | (TODO) | 暂未实现 |

### 1.4 技术实现

**修改文件**: `src/ocr_three_layer_hybrid/vlm_layer.py`

1. **新增页面类型专用提示词**:
   - `HOUSEHOLD_REGISTER_COVER`: 户口本首页专用
   - `HOUSEHOLD_REGISTER_CONTENT`: 户口本人页专用
   - `DIVORCE_CERTIFICATE_COVER`: 离婚证封面/盖章页专用（返回空JSON）
   - `DIVORCE_CERTIFICATE_CONTENT`: 离婚证内容页专用
   - `MARRIAGE_CERTIFICATE_COVER`: 结婚证封面/盖章页专用（返回空JSON）
   - `MARRIAGE_CERTIFICATE_CONTENT`: 结婚证内容页专用

2. **修改 `_build_prompt` 方法**:
   - 签名从 `_build_prompt(doc_type, key_list)` 改为 `_build_prompt(doc_info, key_list)`
   - 优先使用文档类型（细化后）的专用Prompt
   - 回退到基础文档类型的通用Prompt

3. **新增 `_get_base_doc_type` 方法**:
   - 将细化后的文档类型映射回基础类型
   - 例如：`HOUSEHOLD_REGISTER_CONTENT` → `HOUSEHOLD_REGISTER`

4. **更新 `DEFAULT_SUPPORTED_TYPES`**:
   - 添加所有页面类型的DocumentType

## 2. 规则层优化

### 2.1 封面/盖章页处理

**修改文件**: `src/ocr_three_layer_hybrid/rule_layer.py`

- 封面页和盖章页统一返回空字段
- 错误信息：`"封面页/盖章页，跳过提取"`

**支持的页面类型**:
- `DIVORCE_CERTIFICATE_COVER`
- `DIVORCE_CERTIFICATE_STAMP`
- `MARRIAGE_CERTIFICATE_COVER`
- `MARRIAGE_CERTIFICATE_STAMP`

### 2.2 内容页提取

- 离婚证内容页：使用 `_extract_divorce_certificate` 方法
- 结婚证内容页：使用 `_extract_marriage_certificate` 方法
- 户口本首页/个人页：使用 `_extract_household_register` 方法

## 3. 分类器优化

### 3.1 页面类型识别

**修改文件**: `src/ocr_three_layer_hybrid/classifier.py`

1. **离婚证页面识别逻辑**:
   - 内容页：`离婚证字号` + `登记日期`
   - 盖章页：`登记机关` / `婚姻登记专用章` / `予以登记`（优先于封面页检测）
   - 封面页：`离婚证`（无内容页特征）

2. **结婚证页面识别逻辑**:
   - 内容页：`结婚证字号` 或 (`持证人` + `登记日期`)
   - 盖章页：`登记机关` / `婚姻登记专用章` / `予以登记`（优先于封面页检测）
   - 封面页：`结婚证`（无内容页特征，需要至少一个辅助信号）

3. **户口本页面识别逻辑**:
   - 首页：`户别` + `户主姓名`
   - 个人页：`常住人口登记卡`

### 3.2 备选信号增强

**新增 `ADDITIONAL_BACKUP_SIGNALS`**:
```python
DocumentType.DIVORCE_CERTIFICATE: {
    "primary": ["离婚证"],
    "secondary": ["婚姻登记专用章", "予以登记"],
    "min_secondary": 1,
}
```

## 4. 路由配置

**文件**: `src/ocr_three_layer_hybrid/pipeline.py`

所有页面类型的路由配置：

| 文档类型 | 页面类型 | 路由 | 说明 |
|---------|---------|------|------|
| 离婚证 | 封面页 | RULE | 返回空字段 |
| 离婚证 | 内容页 | RULE | 正则提取 |
| 离婚证 | 盖章页 | RULE | 返回空字段 |
| 结婚证 | 封面页 | RULE | 返回空字段 |
| 结婚证 | 内容页 | RULE | 正则提取 |
| 结婚证 | 盖章页 | RULE | 返回空字段 |
| 户口本 | 首页 | RULE | 正则提取 |
| 户口本 | 个人页 | RULE | 正则提取 |

## 5. 测试结果

### 5.1 分类器测试

```
离婚证分类：
  OCR: ('离婚证字号', '登记日期', '持证人') → 离婚证-内容页, 内容页 ✓
  OCR: ('离婚证',) → 离婚证-封面, 封面页 ✓
  OCR: ('离婚证', '婚姻登记专用章') → 离婚证-盖章页, 盖章页 ✓

结婚证分类：
  OCR: ('结婚证字号', '持证人', '登记日期') → 结婚证-内容页, 内容页 ✓
  OCR: ('结婚证', '婚姻登记专用章') → 结婚证-盖章页, 盖章页 ✓

户口本分类：
  OCR: ('户别', '户主姓名', '住址') → 户口本-首页, 首页 ✓
  OCR: ('常住人口登记卡', '姓名', '与户主关系') → 户口本-个人页, 个人页 ✓
```

### 5.2 VLM提示词测试

```
离婚证内容页Prompt: 你是一名专业的离婚证信息提取专家。请仔细识别图片中的离婚证内容页...
离婚证封面页Prompt: 你是一名专业的离婚证信息提取专家。当前页面是离婚证封面页或盖章页...
户口本首页Prompt: 你是一名专业的户口本首页信息提取专家。请仔细识别图片中的户口本首页...
户口本人页Prompt: 你是一名专业的户口本人页信息提取专家。请仔细识别图片中的「常住人口登记卡」...
```

### 5.3 规则层测试

```
离婚证封面页: 封面页/盖章页，跳过提取 字段: {'离婚证字号': '', '持证人': ''} ✓
离婚证盖章页: 封面页/盖章页，跳过提取 字段: {'离婚证字号': '', '持证人': ''} ✓
结婚证封面页: 封面页/盖章页，跳过提取 字段: {'结婚证字号': '', '持证人': ''} ✓
```

## 6. 优化效果

### 6.1 规则层优先
- 封面页、盖章页、内容页都路由到规则层
- 减少VLM层调用，提高处理速度
- 封面/盖章页直接返回空字段，避免无效提取

### 6.2 VLM提示词精准化
- 不同页面类型使用不同的提示词
- 内容页使用详细的字段提取提示词
- 封面/盖章页使用简化提示词（返回空JSON）
- 户口本首页和个人页使用不同的字段列表

### 6.3 分类准确性提升
- 盖章页检测优先于封面页检测
- 新增离婚证盖章页的备选信号
- 更准确的页面类型识别

## 7. 待办事项

- [ ] 户口本索引页的分类和提取（目前未遇到该页面类型）
- [ ] 实际样本测试验证
- [ ] 离婚证正则表达式优化（出生日期、身份证号提取）
