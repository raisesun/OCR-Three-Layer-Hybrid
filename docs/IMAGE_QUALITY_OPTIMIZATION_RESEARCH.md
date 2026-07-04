# 图片质量与分辨率优化研究

**创建日期**: 2026-07-02  
**状态**: 待实施  
**目标**: 找到图片质量和尺寸的最佳平衡点

---

## 一、研究背景

### 1.1 问题陈述
- 高分辨率图片：OCR准确率高，但处理时间长、内存占用大
- 低分辨率图片：处理快，但可能丢失细节，准确率下降
- 需要找到**准确率、速度、文件大小**的平衡点

### 1.2 当前状况
- 默认最大边长：4000px
- 默认JPEG质量：95%
- 未根据图片质量动态调整

---

## 二、研究方向

### 2.1 分辨率与准确率关系

**研究问题**：
- 不同分辨率对OCR准确率的影响
- 找出准确率开始下降的临界点
- 不同文档类型的最佳分辨率

**测试方案**：
```python
resolutions = [4000, 3500, 3000, 2500, 2000, 1500, 1000]
metrics = {
    'ocr_accuracy': 'OCR文本与基线的相似度',
    'extraction_accuracy': '字段提取准确率',
    'processing_time': '处理耗时（秒）',
    'memory_usage': '内存占用（MB）',
    'file_size': '文件大小（KB）',
}
```

**预期结果**：
- 3000-4000px：准确率最高，处理较慢
- 2000-2500px：准确率略有下降，速度提升明显
- 1000-1500px：准确率显著下降，不推荐

### 2.2 压缩质量与准确率关系

**研究问题**：
- JPEG压缩对OCR准确率的影响
- 找出文件大小与准确率的平衡点
- 不同文档类型对压缩的敏感度

**测试方案**：
```python
jpeg_qualities = [95, 85, 75, 65, 55]
metrics = {
    'file_size': '文件大小（KB）',
    'ocr_similarity': 'OCR文本相似度',
    'extraction_accuracy': '字段提取准确率',
}
```

**预期结果**：
- 95%：质量最高，文件最大
- 75-85%：质量损失很小，文件大小显著减少
- 55-65%：质量明显下降，不推荐

### 2.3 图片质量评估

**研究问题**：
- 如何自动评估图片质量（模糊度、噪声水平）
- 根据质量动态调整预处理策略
- 低质量图片是否需要特殊处理

**评估指标**：
```python
def assess_image_quality(image_path):
    """评估图片质量"""
    import cv2
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. 模糊度（拉普拉斯方差）
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # 2. 噪声水平（高斯噪声估计）
    # 使用局部标准差
    noise_level = estimate_noise(gray)
    
    # 3. 对比度
    contrast = gray.std()
    
    # 4. 亮度
    brightness = gray.mean()
    
    return {
        'sharpness': laplacian_var,  # 越高越清晰
        'noise': noise_level,         # 越低越好
        'contrast': contrast,         # 适中最好
        'brightness': brightness,     # 适中最好
    }
```

**质量分级**：
- **高质量**（sharpness > 300, noise < 10）：不需要预处理
- **中等质量**（sharpness 100-300, noise 10-20）：仅去噪
- **低质量**（sharpness < 100, noise > 20）：去噪+对比度增强

---

## 三、实施方案

### 3.1 阶段1：基线测试

**目标**：建立不同分辨率和压缩质量的基线数据

**步骤**：
1. 选择20个代表性样本（覆盖所有文档类型）
2. 对每个样本生成不同分辨率版本（4000, 3000, 2000, 1000px）
3. 对每个样本生成不同压缩质量版本（95%, 85%, 75%, 65%）
4. 运行OCR和字段提取
5. 记录准确率、耗时、文件大小

**输出**：
- 分辨率-准确率曲线
- 压缩质量-准确率曲线
- 耗时-文件大小散点图

### 3.2 阶段2：质量评估模型

**目标**：实现自动质量评估和预处理决策

**步骤**：
1. 收集100+样本，人工标注质量等级
2. 提取图像特征（模糊度、噪声、对比度、亮度）
3. 训练简单分类器（决策树或规则）
4. 验证分类准确率

**输出**：
- 质量评估函数
- 预处理决策规则

### 3.3 阶段3：自适应预处理

**目标**：根据图片质量自动选择预处理配置

**实现**：
```python
class AdaptivePreprocessor:
    def __init__(self):
        self.quality_model = load_quality_model()
    
    def preprocess(self, image_path):
        """根据图片质量自动选择预处理"""
        # 1. 评估质量
        quality = self.assess_quality(image_path)
        
        # 2. 决策
        if quality['sharpness'] > 300 and quality['noise'] < 10:
            # 高质量：不预处理
            config = {'denoise': False, 'contrast': False}
        elif quality['sharpness'] > 100:
            # 中等质量：仅去噪
            config = {'denoise': True, 'contrast': False}
        else:
            # 低质量：去噪+对比度
            config = {'denoise': True, 'contrast': True}
        
        # 3. 执行预处理
        return apply_preprocessing(image_path, config)
```

### 3.4 阶段4：分辨率自适应

**目标**：根据图片尺寸和文档类型自动调整分辨率

**实现**：
```python
def get_optimal_resolution(image_path, doc_type):
    """根据文档类型返回最佳分辨率"""
    # 不同文档类型的最佳分辨率（需要通过实验确定）
    optimal_resolutions = {
        'id_card': 2000,        # 身份证：文字大，2000px足够
        'household_register': 3000,  # 户口本：文字小，需要3000px
        'invoice': 2500,        # 发票：中等
        'contract': 3500,       # 合同：文字密集，需要高分辨率
    }
    
    return optimal_resolutions.get(doc_type, 3000)
```

---

## 四、测试计划

### 4.1 测试样本

**选择标准**：
- 覆盖所有文档类型
- 包含不同质量等级（清晰、模糊、有噪声）
- 包含不同分辨率（高、中、低）

**样本数量**：
- 阶段1：20个样本（快速验证）
- 阶段2：100个样本（训练质量评估模型）
- 阶段3：50个样本（验证自适应预处理）

### 4.2 测试指标

**核心指标**：
1. **字段提取准确率**：最重要的指标
2. **处理耗时**：包括OCR和提取
3. **文件大小**：影响存储和传输

**辅助指标**：
1. **OCR文本相似度**：与基线文本的对比
2. **内存占用**：峰值内存使用
3. **预处理耗时**：预处理本身的开销

### 4.3 测试流程

```python
def run_resolution_test(samples, resolutions=[4000, 3000, 2000, 1000]):
    """测试不同分辨率的影响"""
    results = []
    
    for resolution in resolutions:
        for sample in samples:
            # 1. 缩放图片
            resized_path = resize_image(sample['path'], resolution)
            
            # 2. 运行OCR和提取
            result = process_image(resized_path)
            
            # 3. 记录结果
            results.append({
                'resolution': resolution,
                'sample_id': sample['id'],
                'accuracy': calculate_accuracy(result, sample['baseline']),
                'elapsed': result['elapsed'],
                'file_size': os.path.getsize(resized_path),
            })
    
    return results
```

---

## 五、预期成果

### 5.1 短期（1-2周）

1. **分辨率-准确率曲线**
   - 确定最佳分辨率范围
   - 找出准确率下降的临界点

2. **压缩质量-准确率曲线**
   - 确定最佳压缩质量
   - 找出文件大小与准确率的平衡点

3. **初步建议**
   - 推荐的默认分辨率
   - 推荐的默认压缩质量

### 5.2 中期（2-4周）

1. **质量评估模型**
   - 自动评估图片质量
   - 准确率达到80%+

2. **自适应预处理**
   - 根据质量自动选择预处理
   - 整体准确率提升5-10%

### 5.3 长期（1-2月）

1. **完整的自适应系统**
   - 质量评估 + 预处理决策 + 分辨率调整
   - 端到端自动化

2. **性能优化**
   - 处理速度提升30-50%
   - 文件大小减少40-60%
   - 准确率保持不变或略有提升

---

## 六、风险与挑战

### 6.1 已知风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 测试样本不足 | 结论不可靠 | 扩大样本量到100+ |
| 不同文档类型差异大 | 难以统一标准 | 按文档类型分别优化 |
| 质量评估不准确 | 预处理决策错误 | 使用简单规则，避免复杂模型 |

### 6.2 技术挑战

1. **质量评估的准确性**
   - 模糊度、噪声等指标可能不完全反映OCR效果
   - 需要大量实验确定阈值

2. **文档类型多样性**
   - 不同文档类型的最佳配置可能差异很大
   - 需要为每种类型单独优化

3. **性能开销**
   - 质量评估本身需要时间
   - 需要评估ROI（投入产出比）

---

## 七、下一步行动

### 7.1 立即可做

1. **运行基线测试**
   - 测试10个样本，不同分辨率（4000, 3000, 2000px）
   - 记录准确率、耗时、文件大小
   - 初步分析分辨率-准确率关系

2. **实现质量评估函数**
   - 计算模糊度、噪声水平
   - 对测试样本进行评估
   - 分析质量与准确率的关系

### 7.2 本周计划

1. 完成分辨率测试（20个样本）
2. 完成压缩质量测试（20个样本）
3. 分析结果，确定最佳配置范围
4. 更新实施计划文档

### 7.3 下周计划

1. 实现自适应预处理逻辑
2. 测试自适应预处理效果
3. 与固定配置对比
4. 编写最终报告

---

## 八、参考资源

### 8.1 相关代码

- `src/ocr_three_layer_hybrid/image_preprocessor.py` - 图像预处理
- `src/ocr_three_layer_hybrid/config.py` - 配置管理

### 8.2 相关文档

- `docs/PREPROCESSING_OPTIMIZATION_PLAN.md` - 预处理优化计划
- `docs/analysis_20260702_预处理调优最终报告.md` - 预处理调优结论

### 8.3 参考资料

- OpenCV图像质量评估：https://docs.opencv.org/
- PaddleOCR文档：https://github.com/PaddlePaddle/PaddleOCR
