# OCR引擎替换详细实施方案

**日期**: 2026-07-01  
**目标**: 替换GLM-OCR为PP-StructureV3/PaddleOCR-VL，避免影响现有稳定功能  
**原则**: 分阶段实施、可回滚、有验证标准、最小化影响

---

## 一、实施原则

### 1.1 核心原则

1. **不影响现有功能**: 所有修改都是增量的，不修改现有代码逻辑
2. **可回滚**: 每个阶段都可以快速回滚到上一版本
3. **有验证标准**: 每个阶段都有明确的验证指标
4. **渐进式**: 先验证，再集成，最后替换
5. **并行运行**: 新旧引擎可以并行运行，对比效果

### 1.2 风险控制

| 风险 | 应对措施 |
|------|----------|
| PaddleOCR精度不如预期 | 保留GLM-OCR作为备选，可快速切换 |
| 集成影响现有功能 | 使用功能开关，不影响现有代码路径 |
| 性能问题 | 先在测试环境验证，再上线 |
| 代码冲突 | 使用独立模块，不修改核心代码 |

---

## 二、实施阶段

### Phase 0: 环境准备（第1天）

**目标**: 安装PaddleOCR，验证基础功能

#### 0.1 安装PaddleOCR

```bash
# 创建独立的测试环境（可选）
python3 -m venv paddleocr-env
source paddleocr-env/bin/activate

# 安装PaddleOCR
pip install paddlepaddle
pip install paddleocr

# 验证安装
python3 -c "from paddleocr import PaddleOCR; print('PaddleOCR installed')"
```

#### 0.2 验证基础功能

```python
# test_paddleocr_basic.py
from paddleocr import PaddleOCR

# 测试PP-StructureV3
def test_structure_v3():
    from paddlex import PPStructureV3
    pipeline = PPStructureV3()
    
    # 测试图片
    test_image = "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/4d9fd39863044a649884db86a1b1ecbf.jpg"
    result = pipeline.predict(test_image)
    
    print("PP-StructureV3结果:")
    print(f"  文本长度: {len(result.get('text', ''))}")
    print(f"  文本预览: {result.get('text', '')[:100]}")
    
    return result

# 测试PaddleOCR-VL
def test_paddleocr_vl():
    from paddlex import PaddleOCRVL
    pipeline = PaddleOCRVL()
    
    # 测试图片
    test_image = "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/4d9fd39863044a649884db86a1b1ecbf.jpg"
    result = pipeline.predict(test_image)
    
    print("PaddleOCR-VL结果:")
    print(f"  文本长度: {len(result.get('text', ''))}")
    print(f"  文本预览: {result.get('text', '')[:100]}")
    
    return result

if __name__ == "__main__":
    print("测试PP-StructureV3...")
    test_structure_v3()
    
    print("\n测试PaddleOCR-VL...")
    test_paddleocr_vl()
```

#### 0.3 验证标准

- ✅ PaddleOCR安装成功
- ✅ PP-StructureV3可以正常运行
- ✅ PaddleOCR-VL可以正常运行
- ✅ 输出格式符合预期

**交付物**:
- `scripts/test_paddleocr_basic.py`
- 安装文档

---

### Phase 1: OCR引擎对比测试（第2-3天）

**目标**: 量化对比GLM-OCR vs PaddleOCR的性能

#### 1.1 设计对比实验

```python
# scripts/compare_ocr_engines.py
import time
import json
from pathlib import Path
from typing import Dict, Any

# 测试样本（10张代表性样本）
TEST_SAMPLES = [
    # 身份证
    {"case_id": "BBJZ-2026-0107026", "type": "身份证", 
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/4d9fd39863044a649884db86a1b1ecbf.jpg"},
    
    # 户口本
    {"case_id": "BBJZ-2026-0116023", "type": "户口本",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0116023/1dba4be9c720462f932733f4d4bdfa2d.jpg"},
    
    # 结婚证
    {"case_id": "BBJZ-2026-0107026", "type": "结婚证",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/fccde46a90d642e79466e101cab848.jpg"},
    
    # 购房合同
    {"case_id": "202402270015", "type": "购房合同",
     "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202402270015/e25491d291254874bf854b12515f701f.jpeg"},
    
    # 存量房合同
    {"case_id": "BBJZ-2026-0126003", "type": "存量房合同",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0126003/e9505e57b2d646b9a06c121fe96a8a4a.jpg"},
    
    # 发票
    {"case_id": "202402190050", "type": "发票",
     "path": "/Users/dongsun/Github/sample-OCR/增量房图片资料/202402190050/2f04ef2a8b5244c9b2ff926aa1d0e92b.jpeg"},
    
    # 不动产权证书
    {"case_id": "BBJZ-2026-0129058", "type": "不动产权证书",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0129058/061e171a8b6e41bbbf2b1b562ec5aa26.jpg"},
    
    # 资金监管协议
    {"case_id": "BBJZ-2026-0114007", "type": "资金监管协议",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0114007/34314ee9baa24b398305efa8e1cc7ee7.jpg"},
    
    # 离婚证
    {"case_id": "BBJZ-2026-0113059", "type": "离婚证",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0113059/17938b5ed94a4789a753211c272d3b3a.jpg"},
    
    # 身份证背面
    {"case_id": "BBJZ-2026-0107026", "type": "身份证背面",
     "path": "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/60434e6aacfb41fabafcbfd1406873.jpg"},
]

def test_glm_ocr(image_path: str) -> Dict[str, Any]:
    """测试GLM-OCR"""
    import requests
    import base64
    
    start = time.time()
    
    # 读取图片
    with open(image_path, 'rb') as f:
        img_data = base64.b64encode(f.read()).decode()
    
    # 调用GLM-OCR
    payload = {
        "model": "GLM-OCR",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别图片中的文字"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
                ]
            }
        ],
        "max_tokens": 2000
    }
    
    try:
        response = requests.post("http://localhost:8080/v1/chat/completions", json=payload, timeout=60)
        result = response.json()
        text = result['choices'][0]['message']['content']
        
        elapsed = time.time() - start
        return {
            "success": True,
            "text": text,
            "length": len(text),
            "time": elapsed
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

def test_ppstructure_v3(image_path: str) -> Dict[str, Any]:
    """测试PP-StructureV3"""
    from paddlex import PPStructureV3
    
    start = time.time()
    
    try:
        pipeline = PPStructureV3()
        result = pipeline.predict(image_path)
        text = result.get('text', '')
        
        elapsed = time.time() - start
        return {
            "success": True,
            "text": text,
            "length": len(text),
            "time": elapsed
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

def test_paddleocr_vl(image_path: str) -> Dict[str, Any]:
    """测试PaddleOCR-VL"""
    from paddlex import PaddleOCRVL
    
    start = time.time()
    
    try:
        pipeline = PaddleOCRVL()
        result = pipeline.predict(image_path)
        text = result.get('text', '')
        
        elapsed = time.time() - start
        return {
            "success": True,
            "text": text,
            "length": len(text),
            "time": elapsed
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

def compare_engines():
    """对比所有OCR引擎"""
    results = []
    
    for sample in TEST_SAMPLES:
        print(f"\n测试: {sample['type']} ({sample['case_id']})")
        
        # 测试GLM-OCR
        print("  GLM-OCR...", end=" ")
        glm_result = test_glm_ocr(sample['path'])
        print(f"✓ {glm_result['time']:.2f}s" if glm_result['success'] else f"✗ {glm_result.get('error', '')}")
        
        # 测试PP-StructureV3
        print("  PP-StructureV3...", end=" ")
        pps_result = test_ppstructure_v3(sample['path'])
        print(f"✓ {pps_result['time']:.2f}s" if pps_result['success'] else f"✗ {pps_result.get('error', '')}")
        
        # 测试PaddleOCR-VL
        print("  PaddleOCR-VL...", end=" ")
        vl_result = test_paddleocr_vl(sample['path'])
        print(f"✓ {vl_result['time']:.2f}s" if vl_result['success'] else f"✗ {vl_result.get('error', '')}")
        
        results.append({
            "case_id": sample['case_id'],
            "type": sample['type'],
            "glm_ocr": glm_result,
            "ppstructure_v3": pps_result,
            "paddleocr_vl": vl_result
        })
    
    # 保存结果
    with open('/tmp/ocr_comparison_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 生成报告
    generate_report(results)

def generate_report(results):
    """生成对比报告"""
    print("\n" + "="*70)
    print("OCR引擎对比报告")
    print("="*70)
    
    # 统计
    glm_times = [r['glm_ocr']['time'] for r in results if r['glm_ocr']['success']]
    pps_times = [r['ppstructure_v3']['time'] for r in results if r['ppstructure_v3']['success']]
    vl_times = [r['paddleocr_vl']['time'] for r in results if r['paddleocr_vl']['success']]
    
    glm_lengths = [r['glm_ocr']['length'] for r in results if r['glm_ocr']['success']]
    pps_lengths = [r['ppstructure_v3']['length'] for r in results if r['ppstructure_v3']['success']]
    vl_lengths = [r['paddleocr_vl']['length'] for r in results if r['paddleocr_vl']['success']]
    
    print(f"\nGLM-OCR:")
    print(f"  成功率: {len(glm_times)}/10")
    print(f"  平均耗时: {sum(glm_times)/len(glm_times):.2f}s" if glm_times else "  无成功样本")
    print(f"  平均文本长度: {sum(glm_lengths)/len(glm_lengths):.0f}字" if glm_lengths else "  无成功样本")
    
    print(f"\nPP-StructureV3:")
    print(f"  成功率: {len(pps_times)}/10")
    print(f"  平均耗时: {sum(pps_times)/len(pps_times):.2f}s" if pps_times else "  无成功样本")
    print(f"  平均文本长度: {sum(pps_lengths)/len(pps_lengths):.0f}字" if pps_lengths else "  无成功样本")
    
    print(f"\nPaddleOCR-VL:")
    print(f"  成功率: {len(vl_times)}/10")
    print(f"  平均耗时: {sum(vl_times)/len(vl_times):.2f}s" if vl_times else "  无成功样本")
    print(f"  平均文本长度: {sum(vl_lengths)/len(vl_lengths):.0f}字" if vl_lengths else "  无成功样本")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    compare_engines()
```

#### 1.2 运行对比实验

```bash
# 运行对比实验
python3 scripts/compare_ocr_engines.py

# 查看结果
cat /tmp/ocr_comparison_results.json
```

#### 1.3 验证标准

- ✅ 10张样本全部测试完成
- ✅ 记录每个引擎的速度、成功率、文本长度
- ✅ 生成对比报告

**交付物**:
- `scripts/compare_ocr_engines.py`
- `/tmp/ocr_comparison_results.json`
- 对比报告（控制台输出）

---

### Phase 2: 创建独立的PaddleOCR包装器（第4-5天）

**目标**: 创建独立的PaddleOCR模块，不影响现有代码

#### 2.1 创建包装器模块

```python
# src/ocr_three_layer_hybrid/paddleocr_wrapper.py
"""
PaddleOCR包装器 - 独立模块，不影响现有代码

使用方式:
    from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
    
    wrapper = PaddleOCRWrapper()
    text = wrapper.run_ocr(image_path, engine="ppstructure_v3")
"""

import time
from typing import Optional
from pathlib import Path


class PaddleOCRWrapper:
    """PaddleOCR包装器"""
    
    def __init__(self):
        self._ppstructure_v3 = None
        self._paddleocr_vl = None
    
    def _get_ppstructure_v3(self):
        """延迟加载PP-StructureV3"""
        if self._ppstructure_v3 is None:
            from paddlex import PPStructureV3
            self._ppstructure_v3 = PPStructureV3()
        return self._ppstructure_v3
    
    def _get_paddleocr_vl(self):
        """延迟加载PaddleOCR-VL"""
        if self._paddleocr_vl is None:
            from paddlex import PaddleOCRVL
            self._paddleocr_vl = PaddleOCRVL()
        return self._paddleocr_vl
    
    def run_ocr(
        self, 
        image_path: str, 
        engine: str = "ppstructure_v3",
        doc_type: Optional[str] = None
    ) -> str:
        """
        运行OCR
        
        Args:
            image_path: 图片路径
            engine: OCR引擎 ("ppstructure_v3" 或 "paddleocr_vl")
            doc_type: 文档类型（用于自动选择引擎）
        
        Returns:
            OCR文本
        """
        # 自动选择引擎
        if doc_type and engine == "auto":
            engine = self._select_engine(doc_type)
        
        # 运行OCR
        if engine == "ppstructure_v3":
            return self._run_ppstructure_v3(image_path)
        elif engine == "paddleocr_vl":
            return self._run_paddleocr_vl(image_path)
        else:
            raise ValueError(f"Unknown engine: {engine}")
    
    def _select_engine(self, doc_type: str) -> str:
        """根据文档类型选择引擎"""
        # A/B级文档：使用PP-StructureV3（快）
        fast_types = ["身份证", "结婚证", "离婚证", "户口本", "发票", "银行卡"]
        if doc_type in fast_types:
            return "ppstructure_v3"
        
        # C/D级文档：使用PaddleOCR-VL（精度高）
        return "paddleocr_vl"
    
    def _run_ppstructure_v3(self, image_path: str) -> str:
        """运行PP-StructureV3"""
        try:
            pipeline = self._get_ppstructure_v3()
            result = pipeline.predict(image_path)
            return result.get('text', '')
        except Exception as e:
            print(f"PP-StructureV3 error: {e}")
            return ""
    
    def _run_paddleocr_vl(self, image_path: str) -> str:
        """运行PaddleOCR-VL"""
        try:
            pipeline = self._get_paddleocr_vl()
            result = pipeline.predict(image_path)
            return result.get('text', '')
        except Exception as e:
            print(f"PaddleOCR-VL error: {e}")
            return ""


# 全局实例
_wrapper_instance = None

def get_paddleocr_wrapper() -> PaddleOCRWrapper:
    """获取PaddleOCR包装器实例"""
    global _wrapper_instance
    if _wrapper_instance is None:
        _wrapper_instance = PaddleOCRWrapper()
    return _wrapper_instance


def run_paddleocr(image_path: str, engine: str = "ppstructure_v3") -> str:
    """便捷函数"""
    wrapper = get_paddleocr_wrapper()
    return wrapper.run_ocr(image_path, engine)
```

#### 2.2 测试包装器

```python
# scripts/test_paddleocr_wrapper.py
from ocr_three_layer_hybrid.paddleocr_wrapper import run_paddleocr

# 测试图片
test_images = [
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/4d9fd39863044a649884db86a1b1ecbf.jpg",
    "/Users/dongsun/Github/sample-OCR/存量房图片资料/BBJZ-2026-0107026/fccde46a90d642e79466e101cab848.jpg",
]

for image_path in test_images:
    print(f"\n测试: {Path(image_path).name}")
    
    # 测试PP-StructureV3
    print("  PP-StructureV3:", end=" ")
    text = run_paddleocr(image_path, engine="ppstructure_v3")
    print(f"✓ {len(text)}字")
    
    # 测试PaddleOCR-VL
    print("  PaddleOCR-VL:", end=" ")
    text = run_paddleocr(image_path, engine="paddleocr_vl")
    print(f"✓ {len(text)}字")
```

#### 2.3 验证标准

- ✅ PaddleOCRWrapper类可以正常实例化
- ✅ run_ocr方法可以正常运行
- ✅ PP-StructureV3和PaddleOCR-VL都可以正常工作
- ✅ 不影响现有代码（独立模块）

**交付物**:
- `src/ocr_three_layer_hybrid/paddleocr_wrapper.py`
- `scripts/test_paddleocr_wrapper.py`

---

### Phase 3: 集成测试（第6-7天）

**目标**: 在测试环境中集成PaddleOCR，验证效果

#### 3.1 创建测试脚本

```python
# scripts/test_integration.py
"""
集成测试脚本 - 使用PaddleOCR替换GLM-OCR

使用方式:
    python3 scripts/test_integration.py
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ocr_three_layer_hybrid.paddleocr_wrapper import run_paddleocr
from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 加载测试数据
def load_test_data():
    samples_file = Path('/Users/dongsun/github/OCR-Three-Layer-Hybrid/tests/batch_test_50_samples.json')
    with open(samples_file, 'r', encoding='utf-8') as f:
        return json.load(f)

# 期望类型映射
CERT_CODE_TO_CHINESE = {
    "id_card_front": "身份证",
    "id_card_back": "身份证",
    "marriage": "结婚证",
    "hukou": "户口本",
    "purchase_contract": "购房合同",
    "stock_contract": "存量房合同",
    "property": "不动产权证书",
    "invoice": "发票",
    "fund_supervision": "资金监管协议",
    "divorce_certificate": "离婚证",
    "divorce_agreement": "离婚协议",
}

def main():
    print("=" * 70)
    print("集成测试 - PaddleOCR")
    print("=" * 70)
    print()
    
    # 加载测试数据
    samples = load_test_data()
    
    # 创建OCR服务（使用现有的分类和提取逻辑）
    config = OCRConfig()
    config.enable_vlm_fallback = True
    config.enable_position_extraction = False
    config.enable_vlm_field_fallback = False
    
    service = OCRService(config=config)
    
    # 测试前10张样本
    print("测试前10张样本...")
    print()
    
    correct = 0
    total = 0
    
    for i, sample in enumerate(samples[:10]):
        image_path = sample['image_path']
        expected_en = sample['cert_code']
        expected = CERT_CODE_TO_CHINESE.get(expected_en, expected_en)
        case_id = sample['case_id']
        
        if not Path(image_path).exists():
            continue
        
        total += 1
        
        try:
            # 使用PaddleOCR（而不是GLM-OCR）
            ocr_start = time.time()
            ocr_text = run_paddleocr(image_path, engine="ppstructure_v3")
            ocr_time = time.time() - ocr_start
            
            # 使用现有的分类和提取逻辑
            result = service.process_single(image_path, ocr_text)
            actual = result['classification']['doc_type']
            
            is_correct = (actual == expected)
            if is_correct:
                correct += 1
                status = "✅"
            else:
                status = "❌"
            
            print(f"[{i+1}/10] {status} {case_id}")
            print(f"   期望: {expected}, 实际: {actual}")
            print(f"   OCR耗时: {ocr_time:.2f}s, 文本长度: {len(ocr_text)}字")
            
        except Exception as e:
            print(f"[{i+1}/10] ❌ {case_id} - 错误: {e}")
    
    print()
    print("=" * 70)
    print(f"准确率: {correct}/{total} = {correct/total*100:.1f}%")
    print("=" * 70)

if __name__ == "__main__":
    main()
```

#### 3.2 运行集成测试

```bash
# 运行集成测试
python3 scripts/test_integration.py
```

#### 3.3 验证标准

- ✅ PaddleOCR可以正常集成到现有系统
- ✅ 分类和提取逻辑不受影响
- ✅ 准确率相比GLM-OCR有提升
- ✅ 速度显著提升

**交付物**:
- `scripts/test_integration.py`
- 集成测试报告

---

### Phase 4: 功能开关集成（第8-10天）

**目标**: 通过功能开关支持PaddleOCR，不影响现有功能

#### 4.1 修改配置文件

```python
# src/ocr_three_layer_hybrid/config.py

@dataclass
class OCRConfig:
    # ... 现有配置 ...
    
    # 新增：OCR引擎选择
    ocr_engine: str = "glm_ocr"  # "glm_ocr" | "ppstructure_v3" | "paddleocr_vl" | "auto"
    
    # 新增：是否启用PaddleOCR
    enable_paddleocr: bool = False
```

#### 4.2 修改服务层

```python
# src/ocr_three_layer_hybrid/service.py

class OCRService:
    def __init__(self, config=None, enable_vlm_fallback=True):
        # ... 现有初始化 ...
        
        # 新增：PaddleOCR包装器
        self._paddleocr_wrapper = None
        if self.config.enable_paddleocr:
            from ocr_three_layer_hybrid.paddleocr_wrapper import get_paddleocr_wrapper
            self._paddleocr_wrapper = get_paddleocr_wrapper()
    
    def run_ocr(self, image_path: str) -> str:
        """运行OCR - 支持多引擎"""
        # 根据配置选择引擎
        if self.config.ocr_engine == "ppstructure_v3" and self._paddleocr_wrapper:
            return self._paddleocr_wrapper.run_ocr(image_path, engine="ppstructure_v3")
        elif self.config.ocr_engine == "paddleocr_vl" and self._paddleocr_wrapper:
            return self._paddleocr_wrapper.run_ocr(image_path, engine="paddleocr_vl")
        elif self.config.ocr_engine == "auto" and self._paddleocr_wrapper:
            # 自动选择引擎（需要先分类）
            return self._paddleocr_wrapper.run_ocr(image_path, engine="auto")
        else:
            # 默认使用GLM-OCR
            return self._run_glm_ocr(image_path)
    
    def _run_glm_ocr(self, image_path: str) -> str:
        """运行GLM-OCR（现有逻辑）"""
        # ... 现有的GLM-OCR逻辑 ...
        pass
```

#### 4.3 测试功能开关

```python
# scripts/test_feature_toggle.py

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.service import OCRService

# 测试1: 使用GLM-OCR（默认）
config1 = OCRConfig()
config1.ocr_engine = "glm_ocr"
service1 = OCRService(config=config1)
text1 = service1.run_ocr(test_image)
print(f"GLM-OCR: {len(text1)}字")

# 测试2: 使用PP-StructureV3
config2 = OCRConfig()
config2.ocr_engine = "ppstructure_v3"
config2.enable_paddleocr = True
service2 = OCRService(config=config2)
text2 = service2.run_ocr(test_image)
print(f"PP-StructureV3: {len(text2)}字")

# 测试3: 使用PaddleOCR-VL
config3 = OCRConfig()
config3.ocr_engine = "paddleocr_vl"
config3.enable_paddleocr = True
service3 = OCRService(config=config3)
text3 = service3.run_ocr(test_image)
print(f"PaddleOCR-VL: {len(text3)}字")
```

#### 4.4 验证标准

- ✅ 功能开关可以正常切换引擎
- ✅ 默认使用GLM-OCR（不影响现有功能）
- ✅ 切换到PaddleOCR后可以正常工作
- ✅ 可以回滚到GLM-OCR

**交付物**:
- 修改后的 `config.py`
- 修改后的 `service.py`
- `scripts/test_feature_toggle.py`

---

### Phase 5: 全量测试（第11-14天）

**目标**: 使用PaddleOCR运行完整50张样本测试

#### 5.1 修改评估脚本

```python
# scripts/evaluate_full_50_paddleocr.py

# ... 与 evaluate_full_50.py 相同，但使用PaddleOCR ...

def main():
    # ... 现有逻辑 ...
    
    # 使用PaddleOCR
    config = OCRConfig()
    config.ocr_engine = "ppstructure_v3"  # 或 "paddleocr_vl"
    config.enable_paddleocr = True
    
    service = OCRService(config=config)
    
    # ... 继续现有逻辑 ...
```

#### 5.2 运行全量测试

```bash
# 测试PP-StructureV3
python3 scripts/evaluate_full_50_paddleocr.py --engine ppstructure_v3

# 测试PaddleOCR-VL
python3 scripts/evaluate_full_50_paddleocr.py --engine paddleocr_vl

# 对比GLM-OCR（基线）
python3 scripts/evaluate_full_50.py
```

#### 5.3 验证标准

- ✅ 50张样本全部测试完成
- ✅ 记录准确率、速度、资源占用
- ✅ 与GLM-OCR对比，有显著提升
- ✅ 没有引入新的bug

**交付物**:
- `scripts/evaluate_full_50_paddleocr.py`
- 全量测试报告

---

### Phase 6: 上线决策（第15天）

**目标**: 根据测试结果决定是否全面替换

#### 6.1 决策标准

| 指标 | GLM-OCR（基线） | PaddleOCR目标 | 决策 |
|------|----------------|---------------|------|
| **准确率** | 66% | ≥85% | 达标则替换 |
| **速度** | 27秒/张 | ≤10秒/张 | 达标则替换 |
| **成功率** | ~90% | ≥95% | 达标则替换 |
| **稳定性** | 偶尔超时 | 无超时 | 达标则替换 |

#### 6.2 决策流程

```
如果所有指标达标:
  → 全面替换为PaddleOCR
  → 修改默认配置
  → 更新文档

如果有指标不达标:
  → 分析问题
  → 调整参数或换引擎
  → 重新测试

如果严重不达标:
  → 保留GLM-OCR
  → 继续优化PaddleOCR
  → 或寻找其他方案
```

#### 6.3 上线步骤

```bash
# 1. 修改默认配置
# config.py
ocr_engine: str = "ppstructure_v3"  # 改为PaddleOCR
enable_paddleocr: bool = True

# 2. 提交代码
git add -A
git commit -m "feat: 替换GLM-OCR为PaddleOCR"

# 3. 部署到测试环境
# ...

# 4. 监控运行状态
# ...

# 5. 部署到生产环境
# ...
```

---

## 三、回滚方案

### 3.1 快速回滚

```bash
# 修改配置回滚到GLM-OCR
# config.py
ocr_engine: str = "glm_ocr"  # 改回GLM-OCR
enable_paddleocr: bool = False

# 重启服务
systemctl restart ocr-service
```

### 3.2 代码回滚

```bash
# 如果需要回滚代码
git revert <commit-hash>
```

---

## 四、时间线

| 阶段 | 时间 | 任务 | 交付物 |
|------|------|------|--------|
| **Phase 0** | 第1天 | 环境准备 | 安装文档、测试脚本 |
| **Phase 1** | 第2-3天 | OCR引擎对比 | 对比报告 |
| **Phase 2** | 第4-5天 | 创建包装器 | paddleocr_wrapper.py |
| **Phase 3** | 第6-7天 | 集成测试 | 集成测试报告 |
| **Phase 4** | 第8-10天 | 功能开关集成 | 修改后的config.py、service.py |
| **Phase 5** | 第11-14天 | 全量测试 | 全量测试报告 |
| **Phase 6** | 第15天 | 上线决策 | 决策报告 |

**总时间**: 15天（3周）

---

## 五、风险评估

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| PaddleOCR精度不如预期 | 中 | 高 | 保留GLM-OCR备选 |
| 集成影响现有功能 | 低 | 高 | 功能开关，可快速回滚 |
| 性能问题 | 中 | 中 | 先在测试环境验证 |
| 时间延迟 | 中 | 中 | 分阶段实施，可调整 |

---

## 六、总结

### 6.1 核心原则

1. **不影响现有功能**: 所有修改都是增量的
2. **可回滚**: 每个阶段都可以快速回滚
3. **有验证标准**: 每个阶段都有明确的验证指标
4. **渐进式**: 先验证，再集成，最后替换

### 6.2 关键里程碑

- **Day 1-3**: 环境准备 + 对比测试
- **Day 4-7**: 包装器 + 集成测试
- **Day 8-14**: 功能开关 + 全量测试
- **Day 15**: 上线决策

### 6.3 预期效果

- OCR速度: 27秒 → 0.5-8秒（提升3-50倍）
- 准确率: 66% → 85%+（提升19%+）
- 总耗时: 62.9秒 → 5-15秒（提升4-12倍）

---

**文档版本**: v1.0  
**创建时间**: 2026-07-01  
**作者**: Claude  
**状态**: 待执行
