# 中文证件票据识别 — A+D 混合架构实施文档

> 编写日期：2026-06-27
> 约束：完全离线 + 仅 CPU + Web API
> 核心思路：**快慢分离，各司其职**

---

## 一、方案定位

### 1.1 为什么是 A + D 混合

经过对四个方案的深度分析，我们得出一个关键洞察：

| 文档类型 | 最适合的方案 | 原因 |
|----------|:----------:|------|
| 身份证、结婚证、发票、快递单 | **方案 D 的规则层** | 格式固定，正则 < 1 毫秒，100% 准确率 |
| 户口本、房产证、提单、合同、协议书 | **方案 A 的 PP-ChatOCRv4** | 需要向量检索 + Prompt 工程 + 表格识别 |

**单独用方案 A**：简单文档走完整管线（OCR → 向量 → LLM），浪费算力，处理身份证要 8-38 秒。

**单独用方案 D**：VLM 层阻塞且不确定，工程复杂度高，缺少向量检索。

**A + D 混合**：取两者之长，避两者之短。

### 1.2 核心设计原则

```
┌────────────────────────────────────────────────────────────┐
│                      快慢分离原则                            │
│                                                             │
│   快路径（规则层）：能用正则解决的，绝不用 LLM              │
│   慢路径（PP-ChatOCRv4）：需要语义理解的，才调用 LLM       │
│                                                             │
│   路由决策：文档分类器（关键词匹配）                        │
│   兜底机制：路径失败可切换                                  │
│   统一接口：对外表现为单一 API                              │
└────────────────────────────────────────────────────────────┘
```

---

## 二、整体架构

### 2.1 架构图

```
                    ┌──────────────────────┐
                    │   POST /api/recognize │
                    │   {image, doc_type?}  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  FastAPI 路由层       │
                    │  (统一入口)           │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  文档分类器           │
                    │  (auto 时自动判断)    │
                    │  或用户指定 doc_type  │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐
    │ 快速路径 (3A)    │  │ 慢速路径 (3B) │  │ 未知类型       │
    │ 规则提取器       │  │ PP-ChatOCRv4 │  │ 尝试两条路径   │
    │                 │  │              │  │                │
    │ 身份证          │  │ 户口本       │  │                │
    │ 结婚证          │  │ 房产证       │  │                │
    │ 离婚证          │  │ 购房合同     │  │                │
    │ 发票            │  │ 租房合同     │  │                │
    │ 快递单          │  │ 提单         │  │                │
    └────────┬────────┘  └──────┬───────┘  └───────┬────────┘
             │                  │                   │
             └──────────────────┴───────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  统一响应格式         │
                    │  {doc_type, fields,   │
                    │   extractor_used,     │
                    │   path, confidence}   │
                    └──────────────────────┘
```

### 2.2 路径分配表

| 文档类型 | 代码 | 路径 | 提取方式 | 预计耗时 |
|----------|------|:----:|---------|:--------:|
| 身份证正面 | `id_card_front` | 快 | 正则 | < 1s |
| 身份证背面 | `id_card_back` | 快 | 正则 | < 1s |
| 结婚证 | `marriage_cert` | 快 | 正则 | < 1s |
| 离婚证 | `divorce_cert` | 快 | 正则 | < 1s |
| 发票 | `invoice` | 快 | 正则 + 模板 | < 1s |
| 快递单 | `express_slip` | 快 | 正则 + 模板 | < 1s |
| 户口本 | `household_register` | 慢 | PP-ChatOCRv4 | 5-15s |
| 房产证/不动产证 | `property_cert` | 慢 | PP-ChatOCRv4 | 5-15s |
| 购房合同 | `purchase_contract` | 慢 | PP-ChatOCRv4 | 15-60s |
| 租房合同 | `rental_contract` | 慢 | PP-ChatOCRv4 | 10-30s |
| 提单 | `bill_of_lading` | 慢 | PP-ChatOCRv4 | 5-15s |
| 离婚协议书 | `divorce_agreement` | 慢 | PP-ChatOCRv4 | 10-30s |
| 公证书 | `notary_cert` | 慢 | PP-ChatOCRv4 | 10-30s |

---

## 三、核心组件设计

### 3.1 文档分类器

**职责**：根据 OCR 文本，自动判断文档类型。

**实现策略**：关键词匹配 + 置信度评分

```python
# classifiers/doc_classifier.py

class DocumentClassifier:
    """基于关键词的文档分类器"""

    # 每种文档类型的关键词及其权重
    DOC_PATTERNS = {
        "id_card_front": {
            "keywords": ["公民身份号码", "居民身份证", "出生", "民族", "住址", "姓名"],
            "threshold": 3,  # 命中 3 个及以上关键词即判定
            "negative": ["签发机关"],  # 含这些词则不是正面
        },
        "id_card_back": {
            "keywords": ["签发机关", "有效期", "公民身份号码"],
            "threshold": 2,
        },
        "marriage_cert": {
            "keywords": ["结婚证", "登记日期", "持证人", "配偶", "结婚证字号"],
            "threshold": 2,
        },
        "divorce_cert": {
            "keywords": ["离婚证", "离婚登记", "离婚后"],
            "threshold": 2,
        },
        "invoice": {
            "keywords": ["发票", "发票代码", "发票号码", "税额", "价税合计"],
            "threshold": 2,
        },
        "express_slip": {
            "keywords": ["快递", "运单号", "寄件人", "收件人"],
            "threshold": 2,
        },
        "household_register": {
            "keywords": ["户口簿", "户主", "户号", "常住人口"],
            "threshold": 2,
        },
        "property_cert": {
            "keywords": ["房产证", "不动产权", "权利人", "不动产单元号"],
            "threshold": 2,
        },
        "purchase_contract": {
            "keywords": ["商品房", "购房合同", "出卖人", "买受人", "存量房"],
            "threshold": 2,
        },
        "rental_contract": {
            "keywords": ["租赁合同", "出租方", "承租方", "租金"],
            "threshold": 2,
        },
        "bill_of_lading": {
            "keywords": ["提单", "船名", "航次", "装货港", "卸货港", "Bill of Lading"],
            "threshold": 2,
        },
        "divorce_agreement": {
            "keywords": ["离婚协议", "子女抚养", "财产分割"],
            "threshold": 2,
        },
        "notary_cert": {
            "keywords": ["公证书", "公证处", "公证员", "公证事项"],
            "threshold": 2,
        },
    }

    def classify(self, text: str) -> dict:
        """
        返回：
        {
            "doc_type": "marriage_cert",
            "confidence": 0.85,
            "matched_keywords": ["结婚证", "登记日期", "持证人"],
        }
        """
        scores = {}
        for doc_type, pattern in self.DOC_PATTERNS.items():
            matched = [kw for kw in pattern["keywords"] if kw in text]
            # 排除负面关键词
            if "negative" in pattern:
                if any(neg in text for neg in pattern["negative"]):
                    continue
            scores[doc_type] = len(matched)

        # 取得分最高的
        if not scores or max(scores.values()) == 0:
            return {"doc_type": "unknown", "confidence": 0.0, "matched_keywords": []}

        best_type = max(scores, key=scores.get)
        best_count = scores[best_type]
        threshold = self.DOC_PATTERNS[best_type]["threshold"]

        if best_count < threshold:
            return {"doc_type": "unknown", "confidence": 0.0, "matched_keywords": []}

        # 置信度 = 命中关键词数 / 总关键词数
        total_keywords = len(self.DOC_PATTERNS[best_type]["keywords"])
        confidence = best_count / total_keywords

        matched_keywords = [kw for kw in self.DOC_PATTERNS[best_type]["keywords"] if kw in text]

        return {
            "doc_type": best_type,
            "confidence": round(confidence, 2),
            "matched_keywords": matched_keywords,
        }
```

**关键点**：

1. **多文档冲突处理**：如果多个文档类型得分相同，返回置信度最高的那个，并在响应中标记 `"ambiguous": true`
2. **未知类型兜底**：如果没有任何文档命中阈值，返回 `"unknown"`，由上层决定走哪条路径
3. **性能**：关键词匹配 < 1 毫秒

### 3.2 快速路径：规则提取器

**职责**：处理固定格式文档，用正则表达式提取字段。

#### 3.2.1 提取器基类

```python
# extractors/base.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class BaseExtractor(ABC):
    """所有提取器的基类"""

    # 子类必须定义
    doc_types: List[str] = []  # 支持的文档类型
    path_name: str = ""        # "fast" 或 "slow"

    @abstractmethod
    def extract(self, ocr_text: str, ocr_blocks: List[dict]) -> Dict:
        """
        参数：
            ocr_text: OCR 全文（字符串）
            ocr_blocks: OCR 分块结果（含坐标、置信度）
        返回：
            {
                "fields": {"姓名": "张三", ...},
                "confidence": 0.95,
                "warnings": ["字段 X 未找到"],
            }
        """
        pass

    def validate(self, fields: Dict) -> Dict:
        """字段校验（可选，子类可覆盖）"""
        return {"valid": True, "errors": []}
```

#### 3.2.2 身份证提取器（示例）

```python
# extractors/fast/id_card.py

import re
from .base import BaseExtractor

class IDCardExtractor(BaseExtractor):
    doc_types = ["id_card_front", "id_card_back"]
    path_name = "fast"

    # 正则规则
    RULES = {
        "姓名": re.compile(r"姓\s*名\s*[:：]?\s*([^\s\d]{2,4})"),
        "性别": re.compile(r"性\s*别\s*[:：]?\s*(男|女)"),
        "民族": re.compile(r"民\s*族\s*[:：]?\s*([^\s]{1,4})(?=\s|出生)"),
        "出生": re.compile(r"出\s*生\s*[:：]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
        "住址": re.compile(r"住\s*址\s*[:：]?\s*(.+?)(?=公民身份号码|签发机关|$)"),
        "身份证号": re.compile(r"(\d{17}[\dXx])"),
        "签发机关": re.compile(r"签\s*发\s*机\s*关\s*[:：]?\s*(.+?)(?=有效期|$)"),
        "有效期": re.compile(r"(\d{4}[\.\-]\d{2}[\.\-]\d{2}\s*[-~～至]\s*\d{4}[\.\-]\d{2}[\.\-]\d{2}|长期)"),
    }

    def extract(self, ocr_text: str, ocr_blocks: List[dict]) -> Dict:
        fields = {}
        warnings = []

        # 处理出生日期（三个分组合并）
        birth_match = self.RULES["出生"].search(ocr_text)
        if birth_match:
            fields["出生日期"] = f"{birth_match.group(1)}-{birth_match.group(2).zfill(2)}-{birth_match.group(3).zfill(2)}"
        else:
            warnings.append("出生日期未找到")

        # 其他字段
        for key, pattern in self.RULES.items():
            if key == "出生":
                continue
            match = pattern.search(ocr_text)
            if match:
                fields[key] = match.group(1).strip()
            else:
                warnings.append(f"{key}未找到")

        # 身份证号校验
        if "身份证号" in fields:
            if not self._validate_id_number(fields["身份证号"]):
                warnings.append(f"身份证号校验失败: {fields['身份证号']}")

        # 计算置信度
        total_fields = 6 if "id_card_front" else 2
        found_fields = len([k for k in fields.keys() if k not in ["签发机关", "有效期"]]) \
            if "id_card_front" in str(ocr_text) else len(fields)
        confidence = found_fields / total_fields

        return {
            "fields": fields,
            "confidence": round(confidence, 2),
            "warnings": warnings,
        }

    def _validate_id_number(self, id_number: str) -> bool:
        """身份证号码校验（MOD11-2）"""
        if len(id_number) != 18:
            return False
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = "10X98765432"
        try:
            total = sum(int(id_number[i]) * weights[i] for i in range(17))
            expected = check_codes[total % 11]
            return id_number[-1].upper() == expected
        except:
            return False
```

#### 3.2.3 其他规则提取器

| 文档类型 | 关键正则 | 字段数 | 难度 |
|---------|---------|:------:|:----:|
| 结婚证 | `结婚证字号\s*[:：]?\s*([A-Z0-9\-]+)` | 8 | 低 |
| 离婚证 | `离婚证字号\s*[:：]?\s*([A-Z0-9\-]+)` | 5 | 低 |
| 发票 | `发票代码\s*[:：]?\s*(\d+)` | 8 | 中（含表格） |
| 快递单 | `运单号\s*[:：]?\s*(\d+)` | 7 | 中 |

**每个提取器预估工作量**：0.5-1 天（含测试）

### 3.3 慢速路径：PP-ChatOCRv4

**职责**：处理需要语义理解的文档。

#### 3.3.1 配置（来自可行性报告）

```yaml
# config/pp_chatocrv4_local.yaml
pipeline_name: PP-ChatOCRv4-doc
use_layout_parser: True
use_mllm_predict: False          # CPU 环境关闭多模态 LLM

SubModules:
  LLM_Chat:
    module_name: chat_bot
    model_name: qwen2.5:1.5b
    base_url: "http://localhost:11434/v1"
    api_type: openai
    api_key: "ollama"

  LLM_Retriever:
    module_name: retriever
    model_name: nomic-embed-text
    base_url: "http://localhost:11434/v1"
    api_type: openai
    api_key: "ollama"
    tiktoken_enabled: False

  # ...Prompt 工程模板保持默认
```

#### 3.3.2 各文档类型的 key_list

```python
# extractors/slow/key_lists.py

DOC_KEY_LISTS = {
    "household_register": [
        "户主姓名", "户号", "住址",
        "姓名", "性别", "民族", "出生日期", "身份证号",
        "与户主关系", "文化程度", "职业",
    ],
    "property_cert": [
        "权利人", "共有情况", "坐落",
        "不动产单元号", "权利类型", "权利性质",
        "用途", "面积", "使用期限",
    ],
    "purchase_contract": [
        "合同编号", "甲方（出卖人）", "甲方身份证号",
        "乙方（买受人）", "乙方身份证号",
        "房屋坐落", "建筑面积", "套内面积",
        "房屋总价款", "付款方式", "签订日期",
        "不动产权证号",
    ],
    "rental_contract": [
        "出租方", "承租方", "租赁地址",
        "月租金", "押金", "租期开始", "租期结束",
        "付款方式", "签订日期",
    ],
    "bill_of_lading": [
        "提单号", "发货人", "收货人", "通知人",
        "船名/航次", "装货港", "卸货港",
        "品名", "件数", "重量", "体积",
    ],
    "divorce_agreement": [
        "男方姓名", "男方身份证号",
        "女方姓名", "女方身份证号",
        "登记日期", "子女抚养", "财产分割", "债务处理",
    ],
    "notary_cert": [
        "公证书编号", "申请人", "申请人性别",
        "申请人出生日期", "申请人住址", "申请人身份证号",
        "公证事项", "公证日期", "公证员", "公证处",
    ],
}
```

#### 3.3.3 慢速路径提取器封装

```python
# extractors/slow/chatocr_extractor.py

from paddlex import create_pipeline
from .key_lists import DOC_KEY_LISTS

class ChatOCRExtractor:
    """PP-ChatOCRv4 提取器（懒加载单例）"""

    _instance = None
    _pipeline = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_pipeline(self):
        if self._pipeline is None:
            self._pipeline = create_pipeline(
                pipeline="config/pp_chatocrv4_local.yaml"
            )

    def extract(self, image_path: str, doc_type: str) -> dict:
        """
        返回：
        {
            "fields": {...},
            "confidence": 0.85,
            "warnings": [...],
            "raw_text": "...",
        }
        """
        self._ensure_pipeline()

        key_list = DOC_KEY_LISTS.get(doc_type, [])
        if not key_list:
            return {
                "fields": {},
                "confidence": 0.0,
                "warnings": [f"未知的文档类型: {doc_type}"],
            }

        # Step 1: OCR
        visual_predict_res = list(self._pipeline.visual_predict(
            image_path,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_common_ocr=True,
            use_seal_recognition=True,
            use_table_recognition=True,
        ))
        visual_info_list = [res["visual_info"] for res in visual_predict_res]

        # Step 2: 向量构建（长文档才需要）
        vector_info = None
        if len(visual_info_list) > 1:  # 多页文档
            vector_info = self._pipeline.build_vector(visual_info_list)

        # Step 3: LLM 提取
        chat_result = self._pipeline.chat(
            key_list,
            visual_info_list,
            vector_info=vector_info,
        )

        fields = chat_result.get("chat_res", {})

        # 统计找到的字段数
        found_count = len([v for v in fields.values() if v not in ["未知", "", None]])
        confidence = found_count / len(key_list) if key_list else 0

        warnings = []
        for key in key_list:
            if fields.get(key) in ["未知", "", None]:
                warnings.append(f"{key} 未找到")

        return {
            "fields": fields,
            "confidence": round(confidence, 2),
            "warnings": warnings,
        }
```

---

## 四、统一 API 设计

### 4.1 请求 / 响应格式

**请求**：

```http
POST /api/recognize
Content-Type: multipart/form-data

image: <图片文件>
doc_type: auto | id_card_front | marriage_cert | ...  (可选，默认 auto)
```

**响应**：

```json
{
    "success": true,
    "doc_type": "marriage_cert",
    "doc_type_cn": "结婚证",
    "path": "fast",                          // "fast" 或 "slow"
    "extractor_used": "rule_based",          // 用了哪个提取器
    "classification": {
        "confidence": 0.83,
        "matched_keywords": ["结婚证", "登记日期", "持证人"]
    },
    "fields": {
        "结婚证字号": "J340322-2025-000779",
        "持证人": "尹笑男",
        "姓名1": "尹笑男",
        "姓名2": "凡荣",
        "登记日期": "2025-04-09",
        "国籍": "中国",
        "身份证号1": "340322199512036829",
        "身份证号2": "340322199507018415"
    },
    "raw_text": "持证人 尹笑男\n登记日期 2025年04月09日\n...",
    "confidence": 1.0,
    "warnings": [],
    "timing": {
        "classification_ms": 1,
        "ocr_ms": 3200,
        "extraction_ms": 5,
        "total_ms": 3206
    }
}
```

**错误响应**：

```json
{
    "success": false,
    "error_code": "UNKNOWN_DOC_TYPE",
    "error_message": "无法识别文档类型",
    "suggestion": "请明确指定 doc_type 参数"
}
```

### 4.2 FastAPI 实现

```python
# app/main.py

import time
import tempfile
import os
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse

from app.classifiers.doc_classifier import DocumentClassifier
from app.ocr.paddle_ocr import PaddleOCREngine
from app.extractors.fast.registry import FAST_EXTRACTORS
from app.extractors.slow.chatocr_extractor import ChatOCRExtractor
from app.schemas import DOC_TYPE_CN

app = FastAPI(title="中文证件票据识别 API", version="1.0.0")

# 全局单例（启动时加载）
classifier = DocumentClassifier()
ocr_engine = PaddleOCREngine()
chatocr_extractor = ChatOCRExtractor()

# 快路径文档类型
FAST_DOC_TYPES = set()
for ext in FAST_EXTRACTORS:
    FAST_DOC_TYPES.update(ext.doc_types)

# 慢路径文档类型
SLOW_DOC_TYPES = {
    "household_register", "property_cert", "purchase_contract",
    "rental_contract", "bill_of_lading", "divorce_agreement", "notary_cert",
}


@app.post("/api/recognize")
async def recognize(
    image: UploadFile = File(...),
    doc_type: str = Form("auto"),
):
    start_time = time.time()

    # 1. 保存上传图片
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name

    try:
        # 2. OCR（两条路径都需要）
        t0 = time.time()
        ocr_result = ocr_engine.recognize(tmp_path)
        ocr_ms = int((time.time() - t0) * 1000)

        # 3. 文档分类
        t0 = time.time()
        if doc_type == "auto":
            classification = classifier.classify(ocr_result["text"])
            doc_type = classification["doc_type"]
        else:
            classification = {"doc_type": doc_type, "confidence": 1.0}
        classify_ms = int((time.time() - t0) * 1000)

        # 4. 路由到对应路径
        t0 = time.time()
        if doc_type in FAST_DOC_TYPES:
            # 快路径
            extractor = _get_fast_extractor(doc_type)
            if extractor is None:
                raise HTTPException(400, f"不支持的文档类型: {doc_type}")
            result = extractor.extract(ocr_result["text"], ocr_result["blocks"])
            path = "fast"
            extractor_used = extractor.__class__.__name__
        elif doc_type in SLOW_DOC_TYPES:
            # 慢路径
            result = chatocr_extractor.extract(tmp_path, doc_type)
            path = "slow"
            extractor_used = "PP-ChatOCRv4"
        elif doc_type == "unknown":
            # 未知类型：尝试慢路径（PP-ChatOCRv4 通用能力）
            # 让用户指定 key_list 或者用通用提取
            raise HTTPException(
                400,
                "无法识别文档类型，请明确指定 doc_type 参数",
            )
        else:
            raise HTTPException(400, f"不支持的文档类型: {doc_type}")
        extraction_ms = int((time.time() - t0) * 1000)

        total_ms = int((time.time() - start_time) * 1000)

        return JSONResponse({
            "success": True,
            "doc_type": doc_type,
            "doc_type_cn": DOC_TYPE_CN.get(doc_type, doc_type),
            "path": path,
            "extractor_used": extractor_used,
            "classification": classification,
            "fields": result.get("fields", {}),
            "raw_text": ocr_result["text"],
            "confidence": result.get("confidence", 0.0),
            "warnings": result.get("warnings", []),
            "timing": {
                "classification_ms": classify_ms,
                "ocr_ms": ocr_ms,
                "extraction_ms": extraction_ms,
                "total_ms": total_ms,
            },
        })

    finally:
        os.unlink(tmp_path)


def _get_fast_extractor(doc_type: str):
    for ext in FAST_EXTRACTORS:
        if doc_type in ext.doc_types:
            return ext
    return None


@app.get("/api/doc_types")
async def list_doc_types():
    return {
        "fast": sorted(FAST_DOC_TYPES),
        "slow": sorted(SLOW_DOC_TYPES),
        "all": sorted(FAST_DOC_TYPES | SLOW_DOC_TYPES),
    }


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

---

## 五、项目结构

```
document-recognition/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 主应用
│   ├── config.py                  # 全局配置
│   │
│   ├── classifiers/               # 文档分类器
│   │   ├── __init__.py
│   │   └── doc_classifier.py      # 关键词匹配分类器
│   │
│   ├── ocr/                       # OCR 引擎
│   │   ├── __init__.py
│   │   └── paddle_ocr.py          # PaddleOCR PP-OCRv6 封装
│   │
│   ├── extractors/                # 提取器
│   │   ├── __init__.py
│   │   ├── base.py                # 提取器基类
│   │   │
│   │   ├── fast/                  # 快速路径：规则提取
│   │   │   ├── __init__.py
│   │   │   ├── registry.py        # 提取器注册表
│   │   │   ├── id_card.py         # 身份证提取
│   │   │   ├── marriage_cert.py   # 结婚证提取
│   │   │   ├── divorce_cert.py    # 离婚证提取
│   │   │   ├── invoice.py         # 发票提取
│   │   │   └── express_slip.py    # 快递单提取
│   │   │
│   │   └── slow/                  # 慢速路径：PP-ChatOCRv4
│   │       ├── __init__.py
│   │       ├── chatocr_extractor.py  # ChatOCRv4 封装
│   │       └── key_lists.py          # 各文档类型的 key_list
│   │
│   ├── validators/                # 字段校验
│   │   ├── __init__.py
│   │   └── field_validators.py    # 身份证、发票等校验规则
│   │
│   └── schemas/                   # 数据模型
│       ├── __init__.py
│       └── response.py            # API 响应模型
│
├── config/                        # 配置文件
│   ├── pp_chatocrv4_local.yaml    # PP-ChatOCRv4 本地化配置
│   └── app_config.yaml            # 应用配置（端口、日志等）
│
├── rules/                         # 正则规则（按文档类型）
│   ├── __init__.py
│   ├── patterns_id_card.py
│   ├── patterns_marriage_cert.py
│   └── ...
│
├── tests/                         # 测试
│   ├── test_classifier.py
│   ├── test_fast_extractors.py
│   ├── test_slow_extractor.py
│   └── test_api.py
│
├── test_images/                   # 测试图片
│   ├── id_card/
│   ├── marriage_cert/
│   ├── invoice/
│   └── ...
│
├── scripts/                       # 工具脚本
│   ├── download_models.py         # 模型下载
│   ├── verify_setup.py            # 环境验证
│   └── benchmark.py               # 性能基准测试
│
├── requirements.txt               # Python 依赖
├── Dockerfile                     # Docker 部署
├── docker-compose.yml             # Docker Compose（含 Ollama）
├── run.py                         # 启动脚本
└── README.md                      # 使用说明
```

---

## 六、实施计划

### 第一阶段：基础骨架 + 快速路径（1 周）

**目标**：跑通 OCR + 规则提取，固定格式文档可用

| 任务 | 工作量 | 产出 |
|------|:------:|------|
| 项目骨架搭建 | 0.5 天 | 项目结构 + 依赖 |
| PaddleOCR 引擎封装 | 1 天 | `ocr/paddle_ocr.py` |
| 文档分类器 | 0.5 天 | `classifiers/doc_classifier.py` |
| 身份证提取器 | 0.5 天 | `extractors/fast/id_card.py` |
| 结婚证提取器 | 0.5 天 | `extractors/fast/marriage_cert.py` |
| 离婚证提取器 | 0.5 天 | `extractors/fast/divorce_cert.py` |
| 发票提取器 | 1 天 | `extractors/fast/invoice.py` |
| 快递单提取器 | 1 天 | `extractors/fast/express_slip.py` |
| FastAPI 接口 | 1 天 | `app/main.py` |
| 单元测试 + 集成测试 | 1.5 天 | `tests/` |

**阶段产出**：
- ✅ 5 种固定格式文档可识别
- ✅ API 可访问
- ✅ 每个提取器准确率 > 95%

### 第二阶段：慢速路径接入（1 周）

**目标**：PP-ChatOCRv4 本地化跑通

| 任务 | 工作量 | 产出 |
|------|:------:|------|
| 安装 Ollama + 模型 | 0.5 天 | 本地 LLM 服务 |
| PP-ChatOCRv4 YAML 配置 | 0.5 天 | `config/pp_chatocrv4_local.yaml` |
| 慢速路径封装 | 1 天 | `extractors/slow/chatocr_extractor.py` |
| 7 种文档类型 key_list 定义 | 1 天 | `extractors/slow/key_lists.py` |
| 真实样本测试 | 2 天 | 各文档类型准确率报告 |
| 路由逻辑完善 | 1 天 | 未知类型兜底 + 路径切换 |

**阶段产出**：
- ✅ 全部 12 种文档类型可识别
- ✅ 准确率报告（每种文档类型）
- ✅ 性能基准数据

### 第三阶段：优化 + 生产化（1 周）

**目标**：达到生产环境标准

| 任务 | 工作量 | 产出 |
|------|:------:|------|
| 准确率调优（不达标的文档） | 2 天 | Prompt 调整 + 规则补充 |
| 性能优化 | 1 天 | 懒加载、缓存、异步 |
| Docker 化 | 1 天 | `Dockerfile` + `docker-compose.yml` |
| 监控 + 日志 | 0.5 天 | 结构化日志 + 性能指标 |
| 文档 | 1 天 | README + 部署文档 + API 文档 |
| 端到端测试 | 1.5 天 | 完整测试用例 |

**阶段产出**：
- ✅ 生产就绪的 API 服务
- ✅ 完整文档 + 测试
- ✅ Docker 一键部署

**总工时：3 周**

---

## 七、性能优化

### 7.1 模型懒加载

```python
# extractors/slow/chatocr_extractor.py

class ChatOCRExtractor:
    _pipeline = None  # 首次调用时才加载

    def extract(self, image_path: str, doc_type: str) -> dict:
        if self._pipeline is None:
            logger.info("首次调用，加载 PP-ChatOCRv4 管线...")
            self._pipeline = create_pipeline(...)
            logger.info("管线加载完成")
        # ...
```

**收益**：如果服务启动后只处理身份证（走快路径），PP-ChatOCRv4 的 LLM 永远不会加载，节省 ~1GB 内存。

### 7.2 OCR 结果缓存

```python
import hashlib
from pathlib import Path

class PaddleOCREngine:
    def __init__(self, cache_dir: str = ".cache/ocr"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def recognize(self, image_path: str) -> dict:
        # 用图片 hash 作为缓存 key
        with open(image_path, "rb") as f:
            image_hash = hashlib.md5(f.read()).hexdigest()

        cache_file = self.cache_dir / f"{image_hash}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        # 实际 OCR
        result = self._do_ocr(image_path)

        # 写入缓存
        cache_file.write_text(json.dumps(result, ensure_ascii=False))
        return result
```

**收益**：相同图片重复识别时，OCR 耗时从 3-8 秒降到 < 1 毫秒。

### 7.3 异步处理（长文档）

```python
from fastapi import BackgroundTasks

@app.post("/api/recognize/async")
async def recognize_async(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    doc_type: str = Form(...),
    callback_url: str = Form(...),
):
    task_id = str(uuid.uuid4())

    # 保存任务
    save_task(task_id, image, doc_type, callback_url)

    # 后台处理
    background_tasks.add_task(process_task, task_id)

    return {"task_id": task_id, "status": "pending"}


async def process_task(task_id: str):
    try:
        result = await do_recognize(...)
        # 回调通知
        await httpx.post(callback_url, json={"task_id": task_id, **result})
    except Exception as e:
        await httpx.post(callback_url, json={"task_id": task_id, "error": str(e)})
```

**收益**：长文档（合同）处理不阻塞 API，客户端通过回调获取结果。

### 7.4 各文档类型耗时预算

| 文档类型 | 路径 | OCR | 分类 | 提取 | 总耗时 |
|----------|:----:|:---:|:----:|:----:|:------:|
| 身份证 | 快 | 3-8s | <1ms | <1ms | **3-8s** |
| 结婚证 | 快 | 3-8s | <1ms | <1ms | **3-8s** |
| 发票 | 快 | 3-8s | <1ms | <1ms | **3-8s** |
| 户口本 | 慢 | 3-8s | <1ms | 5-15s | **8-23s** |
| 房产证 | 慢 | 3-8s | <1ms | 5-15s | **8-23s** |
| 购房合同 | 慢 | 3-8s | <1ms | 15-60s | **18-68s** |

---

## 八、风险与应对

### 8.1 已知风险

| 风险 | 影响 | 概率 | 应对 |
|------|------|:----:|------|
| PP-ChatOCRv4 + Qwen2.5-1.5b 准确率不达标 | 慢路径不可用 | 中 | 升级到 3B/7B 模型；或回退到方案 D 的 VLM 层 |
| nomic-embed-text 中文效果差 | 向量检索不准 | 中 | 替换为 bge-large-zh-v1.5（sentence-transformers） |
| 文档分类器误分类 | 走错路径 | 低 | 增加置信度阈值；ambiguous 时返回多个候选 |
| 正则规则覆盖不全 | 部分字段漏提 | 中 | 收集样本持续补充规则；失败时兜底到慢路径 |
| Ollama 服务不稳定 | 慢路径不可用 | 低 | Ollama 自动重启；健康检查 + 报警 |
| 长文档超时 | 用户体验差 | 中 | 异步处理 + 进度回调 |

### 8.2 兜底策略

**策略 1：快路径失败时切慢路径**

```python
if doc_type in FAST_DOC_TYPES:
    result = fast_extractor.extract(...)
    if result["confidence"] < 0.7:
        # 规则提取置信度低，尝试慢路径
        logger.warning(f"快路径置信度低 ({result['confidence']})，切换到慢路径")
        result = chatocr_extractor.extract(tmp_path, doc_type)
```

**策略 2：慢路径失败时降级**

```python
try:
    result = chatocr_extractor.extract(tmp_path, doc_type)
except Exception as e:
    logger.error(f"慢路径失败: {e}")
    # 降级：返回原始 OCR 文本，让用户自己解析
    result = {
        "fields": {},
        "confidence": 0.0,
        "warnings": [f"提取失败: {str(e)}"],
        "raw_text": ocr_result["text"],
        "degraded": True,
    }
```

---

## 九、测试策略

### 9.1 单元测试

```python
# tests/test_fast_extractors.py

def test_id_card_extraction():
    extractor = IDCardExtractor()
    ocr_text = "姓名 张三 性别 男 民族 汉 出生 1990年1月1日 住址 北京市..."
    result = extractor.extract(ocr_text, [])
    assert result["fields"]["姓名"] == "张三"
    assert result["fields"]["身份证号"] == "110101199001011234"
    assert result["confidence"] >= 0.9


def test_classifier():
    classifier = DocumentClassifier()
    text = "结婚证字号 J340322-2025-000779 持证人 尹笑男 登记日期 2025年04月09日"
    result = classifier.classify(text)
    assert result["doc_type"] == "marriage_cert"
    assert result["confidence"] >= 0.8
```

### 9.2 集成测试

```python
# tests/test_api.py

from fastapi.testclient import TestClient

def test_recognize_id_card():
    client = TestClient(app)
    with open("test_images/id_card.jpg", "rb") as f:
        response = client.post(
            "/api/recognize",
            files={"image": f},
            data={"doc_type": "auto"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"]
    assert data["path"] == "fast"
    assert "姓名" in data["fields"]
```

### 9.3 端到端准确率测试

```python
# tests/test_accuracy.py

ACCURACY_TARGETS = {
    "id_card_front": 0.98,
    "marriage_cert": 0.98,
    "invoice": 0.95,
    "household_register": 0.85,
    "purchase_contract": 0.80,
    # ...
}

def test_accuracy_per_doc_type():
    for doc_type, target in ACCURACY_TARGETS.items():
        accuracy = run_accuracy_test(doc_type)
        assert accuracy >= target, f"{doc_type} 准确率 {accuracy} 低于目标 {target}"
```

---

## 十、部署方案

### 10.1 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config
      - ./models:/root/.paddlex
      - ocr_cache:/app/.cache
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    depends_on:
      - ollama
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    # CPU-only 部署
    # 如果有 NVIDIA GPU，可加 deploy.resources.reservations.devices

volumes:
  ollama_data:
  ocr_cache:
```

### 10.2 启动脚本

```bash
#!/bin/bash
# run.sh

# 1. 启动 Ollama（如果未启动）
if ! curl -s http://localhost:11434/v1/models > /dev/null; then
    echo "启动 Ollama..."
    ollama serve &
    sleep 5
fi

# 2. 确保模型已拉取
echo "检查模型..."
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text

# 3. 启动 API 服务
echo "启动 API 服务..."
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 十一、成功标准

### 11.1 准确率标准

| 文档类型 | 路径 | 目标准确率 | 测试样本数 |
|----------|:----:|:---------:|:---------:|
| 身份证 | 快 | ≥ 98% | 50+ |
| 结婚证 | 快 | ≥ 98% | 30+ |
| 离婚证 | 快 | ≥ 95% | 20+ |
| 发票 | 快 | ≥ 95% | 30+ |
| 快递单 | 快 | ≥ 90% | 20+ |
| 户口本 | 慢 | ≥ 85% | 20+ |
| 房产证 | 慢 | ≥ 80% | 20+ |
| 购房合同 | 慢 | ≥ 80% | 20+ |
| 租房合同 | 慢 | ≥ 80% | 20+ |
| 提单 | 慢 | ≥ 75% | 10+ |

### 11.2 性能标准

| 指标 | 目标 |
|------|------|
| 快路径 P95 延迟 | < 10 秒 |
| 慢路径（短文档）P95 延迟 | < 30 秒 |
| 慢路径（长文档）P95 延迟 | < 90 秒 |
| 服务可用性 | ≥ 99% |
| 并发处理能力 | ≥ 5 个请求/分钟 |

### 11.3 工程标准

- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 所有 API 有 OpenAPI 文档
- [ ] 有 Docker 一键部署方案
- [ ] 有完整的 README 和部署文档
- [ ] 有监控和日志
- [ ] 有错误报警机制

---

## 十二、总结

### 12.1 方案核心优势

1. **快慢分离**：简单文档走正则（< 1 秒），复杂文档走 LLM（5-60 秒）
2. **最优准确率**：固定文档 100%（规则），复杂文档 80%+（PP-ChatOCRv4）
3. **工程可控**：避免方案 D 的 VLM 层阻塞问题，避免方案 A 的浪费问题
4. **渐进式部署**：先上线快路径，再接入慢路径
5. **兜底机制**：路径失败可切换，未知类型有处理

### 12.2 与之前方案的对比

| 维度 | 方案 A | 方案 C | 方案 D | **方案 A+D** |
|------|:------:|:------:|:------:|:-----------:|
| 固定文档准确率 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 复杂文档准确率 | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 工程复杂度 | 低 | 最低 | 最高 | **中** |
| 开发工作量 | 1-2 周 | 2-3 周 | 4-6 周 | **3 周** |
| 维护成本 | 低 | 中 | 高 | **中** |

### 12.3 一句话总结

> **取方案 D 的规则层优势（快且准）+ 方案 A 的完备性（向量检索 + Prompt 工程），用文档分类器做路由，用兜底机制保证可靠性。3 周交付，快慢分离，各司其职。**

---

## 附录：参考资源

| 资源 | 路径 / 链接 |
|------|-----------|
| PP-ChatOCRv4 本地化可行性报告 | `PP-ChatOCRv4本地化可行性报告.md` |
| PP-ChatOCRv4 本地化部署详细指南 | `PP-ChatOCRv4本地化部署详细指南.md` |
| 四方案综合对比报告 | `四方案综合对比报告.md` |
| 方案 D 原始文档 | `/Users/dongsun/Github/OCR-PaddleOCR-VL-0.9b/混合架构方案-详细说明.md` |
| 方案 C 实测结果 | `/Users/dongsun/Github/OCR-Paddle-Mac/README.md` |
| PaddleX 源码分析 | `/tmp/PaddleX/paddlex/inference/pipelines/pp_chatocr/pipeline_v4.py` |
