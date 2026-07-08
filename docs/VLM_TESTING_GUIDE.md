# VLM能力测试指南

## 概述

本测试套件提供两个独立的VLM测试脚本，直接测试VLM模型的分类和字段提取能力，不依赖主流程。

## 测试脚本

### 1. VLM分类能力测试

**脚本**: `scripts/test_vlm_classification.py`

**功能**: 测试VLM模型的文档分类准确率

**测试样本**: `tests/vlm_classification_test_samples.json` (5个样本)

**运行方式**:
```bash
# 测试Qwen2.5-VL-3B (端口8083)
python3 scripts/test_vlm_classification.py --model Qwen2.5-VL-3B --port 8083 --limit 5

# 测试Qwen2.5-VL-7B (端口8082)
python3 scripts/test_vlm_classification.py --model Qwen2.5-VL-7B --port 8082 --limit 5
```

**输出指标**:
- 分类准确率 (correct_count / total_samples)
- 平均耗时 (秒/样本)
- 详细分类结果

**结果文件**: `tests/vlm_classification_results_{模型名}.json`

### 2. VLM字段提取能力测试

**脚本**: `scripts/test_vlm_extraction.py`

**功能**: 测试VLM模型的字段提取准确率

**测试样本**: `tests/vlm_extraction_test_samples.json` (9个合同样本)

**运行方式**:
```bash
# 测试Qwen2.5-VL-3B (端口8083)
python3 scripts/test_vlm_extraction.py --model Qwen2.5-VL-3B --port 8083 --limit 9

# 测试Qwen2.5-VL-7B (端口8082)
python3 scripts/test_vlm_extraction.py --model Qwen2.5-VL-7B --port 8082 --limit 9
```

**输出指标**:
- 字段提取准确率 (matched_fields / total_extracted)
- 平均耗时 (秒/样本)
- 详细提取结果

**结果文件**: `tests/vlm_extraction_results_{模型名}.json`

## 测试样本格式

### 分类测试样本
```json
{
  "image_path": "tests/images/xxx.jpeg",
  "case_id": "202406240010",
  "cert_code": "购房合同-首页",
  "ocr_texts": ["OCR文本1", "OCR文本2", ...]
}
```

### 字段提取测试样本
```json
{
  "image_path": "tests/images/xxx.jpeg",
  "case_id": "202406240010",
  "doc_type": "购房合同-首页",
  "key_list": ["合同编号", "买受人", "出卖人", "房屋地址"],
  "ref_fields": {
    "合同编号": "202406240010",
    "买受人": "张三"
  },
  "ocr_texts": ["OCR文本1", "OCR文本2", ...]
}
```

## 测试原理

### 分类测试
1. 加载图片路径和OCR文本
2. 构造提示词，要求VLM判断文档类型
3. 发送图片+提示词到VLM API
4. 比较预测结果与基准标签
5. 计算准确率和耗时

### 字段提取测试
1. 加载图片路径、OCR文本和待提取字段列表
2. 构造提示词，要求VLM提取指定字段
3. 发送图片+提示词到VLM API
4. 解析VLM返回的JSON结果
5. 与基准数据对比，计算字段准确率
6. 记录耗时

## 注意事项

1. **VLM服务必须运行**: 测试前确保对应端口的VLM服务已启动
2. **图片路径正确**: 测试样本中的图片路径必须存在
3. **OCR文本**: 测试脚本会自动从 `batch_test_50_samples.json` 加载OCR文本
4. **结果保存**: 测试结果自动保存到 `tests/` 目录

## 扩展测试样本

如需增加测试样本，编辑对应的JSON文件：

### 分类测试样本
编辑 `tests/vlm_classification_test_samples.json`，添加新样本。

### 字段提取测试样本
编辑 `tests/vlm_extraction_test_samples.json`，添加新样本。

也可以从 `batch_test_50_samples.json` 中提取：
```python
import json

with open('tests/batch_test_50_samples.json', 'r') as f:
    samples = json.load(f)

# 筛选需要的样本并转换为测试格式
```

## 对比分析

运行完两个模型的测试后，可以对比：
- 分类准确率差异
- 字段提取准确率差异
- 速度差异（平均耗时）
- 具体样本的差异表现

## 故障排查

### VLM服务未启动
```
错误: VLM服务未启动 (端口 8083)
```
**解决**: 启动对应端口的VLM服务

### JSON解析失败
```
ERROR: JSON解析失败: ...
```
**解决**: 检查VLM返回格式，可能需要调整提示词

### 图片路径错误
```
FileNotFoundError: [Errno 2] No such file or directory
```
**解决**: 检查测试样本中的 `image_path` 是否正确
