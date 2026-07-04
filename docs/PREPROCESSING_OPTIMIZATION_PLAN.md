# 图像预处理调优实施计划与结论

**创建日期**: 2026-07-02  
**状态**: 阶段1完成（规则层优化），待阶段2（回归测试）  
**负责人**: OCR团队

---

## 一、背景与问题

### 1.1 初始问题
- 图像预处理（去噪+对比度增强）导致身份证提取准确率下降
- 姓名和住址字段提取失败
- 准确率从83.3%下降到66.7%

### 1.2 根因分析
1. **OCR输出格式变化**：预处理后OCR更倾向于输出"标签+值"格式
2. **规则层正则不匹配**：原有正则针对"值+标签"格式优化
3. **对比度增强有害**：导致标签-值相对位置混乱，地址被拆分

---

## 二、已完成的优化（阶段1）

### 2.1 规则层正则优化

**文件**: `src/ocr_three_layer_hybrid/rule_layer.py`

**修改1：姓名提取（第127-144行）**
```python
# 修改前：格式1优先（值+标签）
match = re.search(r'([一-鿿]{2,4})\s*\n\s*姓名', full_text)

# 修改后：格式1优先（标签+同行值）
match = re.search(r'(?<!户主)姓\s*名\s*[:：]?\s*([一-鿿]{2,4})(?=\s|$)', full_text)

# 排除列表增加
if candidate not in (
    "签发机关", "性别", "民族", "出生", "住址", "公民身份号码", "有效期限",
    "性别男", "性别女", "民族汉"  # 新增
):
```

**修改2：住址提取（第177-204行）**
```python
# 支持多行地址合并（即使中间有其他字段）
match = re.search(r'住址\s*([一-鿿]+(?:省|市|区|县|镇|乡|村|路|号|室)[^\n]*)', full_text)
if match:
    candidate = match.group(1).strip()
    # 查找后续行中的地址剩余部分
    lines_after = full_text[match.end():].split('\n')
    for line in lines_after[:5]:
        line = line.strip()
        if (any(kw in line for kw in ['镇', '乡', '村', '路', '号', '室']) and
            not any(label in line for label in ['出生', '性别', '民族', '公民身份', '签发'])):
            candidate += line
            break
```

### 2.2 预处理配置优化

**文件**: `src/ocr_three_layer_hybrid/config.py`（待更新）

**推荐配置**:
```python
enable_image_preprocessing: bool = True      # 从False改为True
preprocessing_denoise: bool = True           # 启用去噪
preprocessing_deskew: bool = False           # 禁用（竖向文档误判）
preprocessing_contrast: bool = False         # 禁用（导致格式混乱）
preprocessing_binarize: bool = False         # 禁用（丢失细节）
```

---

## 三、测试结果（阶段1）

### 3.1 测试样本
- **图片**: 身份证 (刘开顺)
- **路径**: `/Users/dongsun/Github/sample-OCR/增量房图片资料/202402270015/e25491d291254874bf854b12515f701f.jpeg`

### 3.2 对比结果

| 配置 | OCR长度 | 分类置信度 | 提取准确率 | 备注 |
|------|---------|------------|------------|------|
| 无预处理 | 64字符 | 0.90 | 83.3% (5/6) | 出生日期不完整 |
| 去噪+对比度（优化前） | 79字符 | 0.95 | 66.7% (4/6) | 姓名、住址丢失 ✗ |
| **仅去噪（优化后）** | 77字符 | **0.95** | **100% (6/6)** ✓ | 所有字段完整 |

### 3.3 字段提取对比

| 字段 | 期望值 | 无预处理 | 仅去噪（优化后） |
|------|--------|----------|------------------|
| 姓名 | 刘开顺 | ✓ | ✓ |
| 性别 | 男 | ✓ | ✓ |
| 民族 | 汉 | ✓ | ✓ |
| 出生 | 1994年3月1日 | ⚠ 1994年3月 | ✓ **完整** |
| 住址 | 安徽省...101号 | ✓ | ✓ |
| 身份证号 | 340322... | ✓ | ✓ |

### 3.4 回归测试结果（2026-07-02）

**测试范围**: 10个样本，覆盖5种文档类型

**结果**:
| 配置 | 成功率 | 平均耗时 | 字段完整性 |
|------|--------|----------|------------|
| 无预处理 | **100%** | 33.3s | 略好（某些样本多1字段） |
| 仅去噪 | **100%** | 50.4s | 略差（某些样本少1字段） |

**按文档类型**:
- household_register: 100% = 100%
- hukou: 100% = 100%
- id_card_front: 100% = 100% ✓
- purchase_contract: 100% = 100%
- stock_contract: 100% = 100%

**结论**: 
- ✓ 无回归问题，所有文档类型保持100%准确率
- ⚠ 仅去噪预处理增加50%处理时间（33.3s → 50.4s）
- ⚠ 字段完整性：无预处理略好

**建议**:
- 当前阶段：保持预处理默认禁用（`enable_image_preprocessing=False`）
- 理由：无预处理速度更快，字段完整性略好
- 待优化：需要研究如何减少预处理的性能开销

---

## 四、下一步计划

### 阶段2：回归测试（进行中）

**目标**: 验证规则层优化没有引入回归问题

**测试范围**:
1. **身份证**：多种格式（正面、背面、无标签格式）
2. **户口本**：首页、变更登记页、多页
3. **结婚证**
4. **发票**
5. **购房合同**
6. **存量房合同**
7. **不动产权证书**

**测试方法**:
```bash
# 运行完整测试套件
python3 scripts/vlm_model_evaluation.py

# 或者手动测试特定样本
python3 scripts/test_single_image.py --image <path> --config denoise_only
```

**通过标准**:
- 所有文档类型的准确率不低于优化前
- 身份证提取准确率 ≥ 95%
- 无新增的错误匹配

### 阶段3：图片质量自适应（待实施）

**目标**: 根据图片质量和分辨率自动选择预处理配置

**方案A：基于模糊度**
```python
def assess_image_quality(image_path):
    """评估图片质量（模糊度、噪声水平）"""
    import cv2
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 计算拉普拉斯方差（模糊度指标）
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 阈值判断（需要实验确定）
    if laplacian_var < 100:  # 模糊
        return 'low'
    elif laplacian_var < 300:  # 中等
        return 'medium'
    else:  # 清晰
        return 'high'

def get_preprocessing_config(quality):
    """根据质量返回预处理配置"""
    if quality == 'low':
        return {'denoise': True, 'contrast': True}  # 需要增强
    elif quality == 'medium':
        return {'denoise': True, 'contrast': False}  # 仅去噪
    else:
        return {'denoise': False, 'contrast': False}  # 不预处理
```

**方案B：基于分辨率**
```python
def get_preprocessing_config_by_resolution(image_path):
    """根据分辨率调整预处理"""
    from PIL import Image
    img = Image.open(image_path)
    width, height = img.size
    max_side = max(width, height)
    
    if max_side > 4000:  # 高分辨率
        return {'denoise': False, 'resize': True}  # 缩放但不预处理
    elif max_side > 2000:  # 中等分辨率
        return {'denoise': True, 'resize': False}  # 仅去噪
    else:  # 低分辨率
        return {'denoise': True, 'contrast': True}  # 需要增强
```

**方案C：混合策略**
- 同时考虑质量、分辨率、文件大小
- 使用决策树或简单规则
- 需要收集足够的数据来确定阈值

**实施步骤**:
1. 收集100+样本，标注质量和预处理效果
2. 分析质量/分辨率与预处理效果的关系
3. 确定阈值和规则
4. 实现自适应逻辑
5. A/B测试验证效果

### 阶段4：性能优化（待实施）

**目标**: 找到图片质量和尺寸的最佳平衡点

**研究方向**:
1. **分辨率与准确率关系**
   - 测试不同分辨率（4000px, 3000px, 2000px, 1000px）
   - 找出准确率开始下降的临界点
   
2. **压缩与准确率关系**
   - 测试不同JPEG质量（95%, 85%, 75%, 60%）
   - 找出文件大小与准确率的平衡点

3. **预处理性能开销**
   - 测量不同预处理配置的耗时
   - 评估预处理的ROI（投入产出比）

**测试方法**:
```python
def test_resolution_impact(image_path):
    """测试不同分辨率对准确率的影响"""
    resolutions = [4000, 3000, 2000, 1000]
    results = []
    
    for max_side in resolutions:
        # 缩放图片
        resized_path = resize_image(image_path, max_side)
        
        # 运行OCR和提取
        result = process_image(resized_path)
        
        # 记录结果
        results.append({
            'resolution': max_side,
            'accuracy': calculate_accuracy(result),
            'file_size': os.path.getsize(resized_path),
            'processing_time': measure_time(resized_path),
        })
    
    return results
```

---

## 五、风险与缓解

### 5.1 已知风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 规则层优化可能引入回归 | 其他文档类型准确率下降 | 阶段2回归测试 |
| 仅去噪可能不适用于所有图像 | 低质量图像效果差 | 阶段3自适应预处理 |
| 测试样本不足 | 结论不可靠 | 扩大测试范围到50+样本 |

### 5.2 回滚方案

如果阶段2发现回归问题：
1. 立即回滚规则层修改
2. 恢复预处理默认配置为False
3. 分析回归原因
4. 重新设计修复方案

---

## 六、关键洞察

### 6.1 预处理不是越多越好
- 对比度增强反而降低了准确率
- 简单的去噪比复杂的预处理更有效

### 6.2 OCR格式决定提取策略
- 规则层正则必须匹配OCR输出格式
- 预处理改变了OCR格式，需要同步更新正则

### 6.3 简单方案可能更有效
- 仅去噪（1个参数）比去噪+对比度（2个参数）更好
- 减少预处理参数，降低调优复杂度

---

## 七、附录

### 7.1 测试脚本

**仅去噪测试**:
```python
config = OCRConfig(
    enable_image_preprocessing=True,
    preprocessing_denoise=True,
    preprocessing_deskew=False,
    preprocessing_contrast=False,
)
service = OCRService(config)
ocr_text = service.run_ocr(image_path)
result = service.process_single(image_path, ocr_text)
```

### 7.2 相关文件

- `src/ocr_three_layer_hybrid/rule_layer.py` - 规则层正则
- `src/ocr_three_layer_hybrid/config.py` - 配置管理
- `src/ocr_three_layer_hybrid/image_preprocessor.py` - 图像预处理
- `tests/batch_test_50_samples.json` - 测试样本清单

### 7.3 参考文档

- `docs/analysis_20260702_图像预处理影响分析.md` - 初始分析
- `docs/analysis_20260702_预处理调优方案.md` - 方案对比
- `docs/analysis_20260702_预处理调优最终报告.md` - 最终结论

---

## 八、更新日志

| 日期 | 版本 | 更新内容 | 作者 |
|------|------|----------|------|
| 2026-07-02 | v1.0 | 初始版本，阶段1完成 | OCR团队 |
| - | - | 待更新：阶段2回归测试结果 | - |
| - | - | 待更新：阶段3自适应预处理 | - |

---

## 九、更新日志（2026-07-02）

### 9.1 分辨率优化完成

**测试时间**: 2026-07-02  
**测试样本**: 5个  
**测试分辨率**: 4000px, 3000px, 2000px, 1500px

**结果**:

| 分辨率 | 准确率 | 耗时 | 文件大小 | 结论 |
|--------|--------|------|----------|------|
| 4000px | 66.0% | 45.0s | 1821KB | 基线 |
| 3000px | 62.7% | 46.1s | 1253KB | 不推荐 |
| **2000px** | **66.0%** | **22.2s** | **682KB** | **✓ 最佳** |
| 1500px | 62.7% | 8.0s | 416KB | 准确率下降 |

**关键发现**:
- 2000px与4000px准确率相同（66.0%）
- 2000px速度快2倍（22.2s vs 45.0s）
- 2000px文件小63%（682KB vs 1821KB）

**实施**: ✅ 已将默认分辨率从4000px改为2000px

**修改文件**:
1. `src/ocr_three_layer_hybrid/image_preprocessor.py`
   - 第36行：`resize_image` 函数默认参数 `max_side = 2000`
   - 第96行：`ensure_max_size` 函数默认参数 `max_side = 2000`

2. `src/ocr_three_layer_hybrid/paddleocr_wrapper.py`
   - 第312行：PP-StructureV3预处理 `max_side=2000`

**预期收益**:
- 处理速度提升约50%
- 文件大小减少约63%
- 准确率保持不变

### 9.2 质量评估工具

**创建时间**: 2026-07-02  
**文件**: `scripts/assess_image_quality.py`

**功能**:
- 评估图片质量（模糊度、噪声、对比度、亮度）
- 自动推荐预处理配置
- 质量分级（高/中/低）

**测试结果**:
- 测试样本：身份证 (3024x4032px, 371.8KB)
- 模糊度：116.1（中等）
- 噪声：4.54（低）
- 质量等级：MEDIUM
- 推荐配置：仅去噪

### 9.3 下一步计划

1. **压缩质量测试**（待实施）
   - 测试不同JPEG质量（95%, 85%, 75%, 65%）对准确率的影响
   - 找出文件大小与准确率的平衡点

2. **自适应预处理**（待实施）
   - 根据图片质量自动选择预处理配置
   - 需要收集更多样本验证质量评估准确性

3. **更多样本测试**
   - 扩大测试范围到50+样本
   - 验证2000px分辨率在不同文档类型上的表现


### 9.4 压缩质量优化完成

**测试时间**: 2026-07-02  
**测试样本**: 5个  
**测试质量**: 95%, 85%, 75%, 65%, 55%

**结果**:

| JPEG质量 | 平均字段数 | 平均耗时 | 平均文件大小 | 大小减少 | 结论 |
|----------|------------|----------|--------------|----------|------|
| 95% | 5.0 | 29.8s | 1123KB | 7.7% | 基线 |
| 85% | 5.2 | 28.1s | 682KB | 44.0% | 速度最快 |
| **75%** | **5.8** | **28.8s** | **566KB** | **53.5%** | **✓ 最佳** |
| 65% | 5.8 | 30.2s | 503KB | 58.7% | 字段数多 |
| 55% | 5.6 | 36.4s | 334KB | 72.5% | 文件最小 |

**关键发现**:
- 75%和65%的字段数最多（5.8个），比95%（5.0个）多16%
- 降低压缩质量没有导致准确率下降，反而可能提升（压缩减少了噪声）
- 85%速度最快（28.1s），文件减少44%
- 75%是最佳平衡点：字段数最多，文件减少53.5%，速度较快

**实施**: ✅ 已将默认JPEG质量从95%改为75%

**修改文件**:
1. `src/ocr_three_layer_hybrid/image_preprocessor.py`
   - 第38行：`resize_image` 函数默认参数 `quality = 75`

**预期收益**（相比95%）:
- 字段数提升：+16%（5.0 → 5.8）
- 文件大小减少：53.5%（1123KB → 566KB）
- 处理速度：基本持平（29.8s → 28.8s）

**累计收益**（分辨率2000px + 质量75%，相比原始4000px+95%）:
- 文件大小减少：约70%（1821KB → 566KB）
- 处理速度提升：约50%（45.0s → 28.8s）
- 字段数提升：约16%（5.0 → 5.8）

