# OCR 两层混合架构 - 技术架构文档

> **版本**: v2.1.0 | **日期**: 2026-07-09 | **状态**: 生产就绪

---

## 目录

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [项目结构](#项目结构)
4. [核心模块详解](#核心模块详解)
5. [关键技术说明](#关键技术说明)
6. [数据流](#数据流)
7. [部署与配置](#部署与配置)

---

## 项目概述

### 架构演进

| 版本 | 时间 | 关键变更 |
|------|------|---------|
| v1.0 | 2026-06 | 初始三层架构：RULE + LLM (PP-ChatOCRv4) + VLM |
| v2.0 | 2026-07-05 | 移除 LLM 层、VLM 分类兜底、PaddleOCR-VL 备用引擎 |
| v2.1.0 | 2026-07-09 | API 服务层独立、租户配额、工厂模式重构；架构重命名为"两层 + 字段级VLM重试" |

### 当前架构（v2.1.0）

- **ProcessingLayer** 仅含 `RULE` + `VLM` 两种处理层（LLM 已彻底移除）
- **OCRConfig** 仅含 `vlm_service` + `qwen_vl_service`（无 ClassificationServiceConfig、无 LLMServiceConfig、无 ThresholdsConfig）
- **API Key 认证** 通过 `APIKeyAuthenticator` 类（Bearer Token 模式，非函数）
- **工厂模式** `create_app()` 注入 OCRService、TaskManager、APIKeyAuthenticator
- **SQLite** WAL 模式 + thread-local 连接，保证并发安全
- **租户配额** 纯 SQL JOIN 查询，不扫描文件系统
- **多页文档** 逐页独立分类（不再复用首页分类结果）

### 支持的文档类型

**第一类：标准证件**
- 身份证（正面/背面）
- 结婚证（封面/内容页/盖章页）
- 离婚证（封面/内容页/盖章页）
- 户口本（首页/个人页）
- 不动产权证书（首页/内容页/附图页）

**第二类：标准单证**
- 发票

**第三类：合同/协议**
- 购房合同（首页/内容页/签署页）
- 存量房合同（首页/内容页/签署页）
- 资金监管协议（首页/信息页/签章页）
- 资金监管凭证
- 离婚协议书
- 公证书
- 委托书

---

## 系统架构

### 整体分层

```
┌─────────────────────────────────────────────────────────────────────┐
│                      API 服务层 (FastAPI)                            │
│  src/ocr_api/                                                       │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────────────────┐ │
│  │ auth.py  │  │ server.py │  │ routes/                          │ │
│  │ APIKey   │  │ create_   │  │   health.py  ocr.py              │ │
│  │ Authenti-│  │ app()     │  │   task.py    quota.py            │ │
│  │ cator    │  │ 工厂模式  │  │                                  │ │
│  └──────────┘  └───────────┘  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ common/schemas.py    — Pydantic 请求/响应模型                  │   │
│  │ common/task_manager.py — SQLite 异步任务队列 + 租户配额        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    核心领域层                                         │
│  src/ocr_three_layer_hybrid/                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ service.py — OCRService（对外公开 API）                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ pipeline.py — PlanEPlusPipeline 编排器                        │   │
│  │  ├── classifier.py — 6 级联关键词分类器                        │   │
│  │  ├── rule_layer.py — 正则提取层（分发到 4 个领域提取器）       │   │
│  │  │   └── extractors/                                         │   │
│  │  │       ├── personal_id (身份证/结婚证/离婚证)               │   │
│  │  │       ├── household_property (户口本/房产证)               │   │
│  │  │       ├── financial (发票/合同/资金监管)                    │   │
│  │  │       └── agreement (离婚协议/公证书/委托书)               │   │
│  │  ├── vlm_layer.py — VLM 视觉模型提取                          │   │
│  │  └── vlm_fallback.py — 字段级 VLM 兜底                        │   │
│  │  position_extractor.py — PaddleOCR 坐标位置提取               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 基础设施层                                                    │   │
│  │ external_services.py | paddleocr_wrapper.py | prompt_templates │   │
│  │ field_validator.py | json_utils.py | text_preprocessor.py     │   │
│  │ image_preprocessor.py | ui_metadata.py                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 处理层架构

```
图片输入
    │
    ▼
[文档分类] KeywordDocumentClassifier（6 级联关键词）
    │
    ▼
[路由决策] field_config.py 字段优先级 → 决定 RULE / VLM
    │
    ├────────────────────────────────────────────┐
    ▼                                            ▼
[RULE 层] 正则提取                      [VLM 层] 视觉模型提取
    │                                            │
    ▼                                            ▼
[FieldValidator 校验]                              │
    │                                            │
    ├─ 通过 → 输出                                │
    └─ 失败 → [VLM 字段级兜底] ──────────────────┘
                      │
                      ▼
                  输出结果
```

---

## 项目结构

```
src/
├── ocr_api/                              # API 服务层（FastAPI）
│   ├── common/
│   │   ├── auth.py                       # APIKeyAuthenticator 类（Bearer Token 认证）
│   │   ├── schemas.py                    # Pydantic 请求/响应模型
│   │   │                                 #   - APIResponse
│   │   │                                 #   - AsyncSubmitResponse
│   │   │                                 #   - TaskStatusResponse
│   │   │                                 #   - QuotaResponse
│   │   └── task_manager.py               # SQLite 异步任务队列 + 租户配额
│   │                                     #   - WAL 模式
│   │                                     #   - thread-local 连接
│   │                                     #   - 纯 SQL JOIN 配额查询
│   └── ocr/
│       ├── server.py                     # create_app() 工厂函数（支持依赖注入）
│       └── routes/
│           ├── health.py                 # 健康检查端点
│           ├── ocr.py                    # OCR 同步/异步处理端点
│           ├── task.py                   # 任务状态查询端点
│           └── quota.py                  # 租户配额查询端点
│
└── ocr_three_layer_hybrid/               # 核心领域层
    ├── interfaces.py                     # DocumentType, ExtractionResult, BaseExtractor ABC
    ├── config.py                         # VLMServiceConfig, QwenVLServiceConfig, OCRConfig
    ├── field_config.py                   # 文档类型 → 字段优先级配置
    ├── service.py                        # OCRService（公开 API）
    ├── pipeline.py                       # PlanEPlusPipeline 编排器
    ├── classifier.py                     # 6 级联关键词分类器
    ├── rule_layer.py                     # 正则提取层（分发到 4 个领域提取器）
    ├── vlm_layer.py                      # VLM 视觉模型提取
    ├── vlm_fallback.py                   # 字段级 VLM 兜底
    ├── position_extractor.py             # PaddleOCR 坐标位置提取
    ├── extractors/                       # 领域提取器
    │   ├── base_extractor.py             # 基础提取器
    │   ├── personal_id_extractor.py      # 身份证/结婚证/离婚证
    │   ├── household_property_extractor.py # 户口本/房产证
    │   ├── financial_extractor.py        # 发票/合同/资金监管
    │   └── agreement_extractor.py        # 离婚协议/公证书/委托书
    └── 基础设施
        ├── external_services.py          # VLM API 客户端
        ├── paddleocr_wrapper.py          # PaddleOCR 封装
        ├── prompt_templates.py           # VLM Prompt 模板（按文档类型）
        ├── field_validator.py            # 字段格式校验器
        ├── json_utils.py                 # JSON 解析工具
        ├── text_preprocessor.py          # 文本预处理
        ├── image_preprocessor.py         # 图像预处理
        └── ui_metadata.py               # UI 元数据生成
```

---

## 核心模块详解

### API 服务层

#### `common/auth.py` — APIKeyAuthenticator

```python
class APIKeyAuthenticator:
    """Bearer Token 认证器"""
    def __init__(self, api_keys: List[str]):
        self._valid_keys = set(api_keys)

    def verify(self, token: str) -> bool:
        """验证 Bearer Token 是否有效"""
        return token in self._valid_keys
```

- 注入到 `create_app()` 工厂函数
- FastAPI 依赖项通过 `Depends()` 使用

#### `common/task_manager.py` — 异步任务队列

- **SQLite WAL 模式**：并发读写不阻塞
- **thread-local 连接**：每个线程独立连接，避免跨线程共享问题
- **租户配额**：纯 SQL JOIN 查询（`tenants` 表 JOIN `tasks` 表），不扫描文件系统
- **任务状态**：pending → running → completed / failed

#### `ocr/server.py` — 工厂函数

```python
def create_app(
    ocr_service: OCRService,
    task_manager: TaskManager,
    authenticator: APIKeyAuthenticator,
) -> FastAPI:
    """创建 FastAPI 应用（支持依赖注入）"""
```

#### `common/schemas.py` — Pydantic 模型

```python
class APIResponse(BaseModel):
    """同步 OCR 响应"""

class AsyncSubmitResponse(BaseModel):
    """异步提交响应（返回 task_id）"""

class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""

class QuotaResponse(BaseModel):
    """租户配额响应"""
```

---

### 核心领域层

#### `interfaces.py` — 接口定义

```python
class DocumentType(str, Enum):
    """支持的文档类型"""
    ID_CARD = "身份证"
    ID_CARD_FRONT = "身份证-正面"
    ID_CARD_BACK = "身份证-背面"
    MARRIAGE_CERTIFICATE = "结婚证"
    # ... 更多类型

class PageType(str, Enum):
    """页面类型"""
    COVER = "封面页"
    CONTENT = "内容页"
    STAMP = "盖章页"
    FIRST_PAGE = "首页"
    PERSONAL_PAGE = "个人页"
    UNKNOWN = "未知页"

class ProcessingLayer(str, Enum):
    """处理层类型（v2.0+ 仅 RULE + VLM）"""
    RULE = "rule"
    VLM = "vlm"
    # LLM 已移除

@dataclass
class ExtractionResult:
    """字段提取结果"""
    doc_type: DocumentType
    layer: ProcessingLayer
    fields: Dict[str, str]
    success: bool
    time_cost: float
    vlm_fallback_triggered: bool = False
    vlm_fallback_fields: List[str] = field(default_factory=list)
    field_conflicts: List[FieldConflict] = field(default_factory=list)

class BaseExtractor(ABC):
    """提取器抽象基类"""
    @abstractmethod
    def extract(self, doc_info, key_list, ocr_text) -> Dict[str, str]: ...
```

#### `config.py` — 配置管理

```python
@dataclass
class OCRConfig:
    """OCR 配置（v2.1.0：无 ClassificationServiceConfig / LLMServiceConfig / ThresholdsConfig）"""
    vlm_service: VLMServiceConfig
    qwen_vl_service: QwenVLServiceConfig
```

#### `field_config.py` — 字段优先级

```python
class FieldPriority(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"

@dataclass
class FieldConfig:
    name: str
    priority: FieldPriority
    sources: List[str]   # 提取源优先级：["rule", "vlm"]

@dataclass
class DocumentFieldConfig:
    required_fields: List[FieldConfig]
    optional_fields: List[FieldConfig]
```

#### `classifier.py` — 6 级联关键词分类器

```
阶段0: 多文档冲突检测（合同级强信号）
阶段1: 标准证件强信号（常住人口登记卡、公民身份号码...）
阶段1.5: 备选强信号（持证人+登记日期）
阶段1.6: 更多备选信号
阶段2: 标准单证强信号（发票代码+发票号码）
阶段3: 合同字段组合（买受人+出卖人+价款）
```

**v2.1.0 改进**：多页文档逐页独立分类，不再复用首页分类结果。

#### `pipeline.py` — PlanEPlusPipeline

```python
class PlanEPlusPipeline:
    def process(self, image_path, ocr_texts, doc_info=None) -> ExtractionResult:
        """
        1. 文档分类 → DocumentInfo
        2. 路由决策 → RULE / VLM
        3. 字段提取 → ExtractionResult
        4. VLM 字段级兜底（可选）
        5. 返回结果
        """
```

**默认层路由**（v2.1.0）：

| 文档类型 | 处理层 | 说明 |
|---------|--------|------|
| 身份证 | RULE | 正则提取 |
| 户口本 | RULE | 位置感知提取 |
| 购房合同 | RULE | 规则层优先（v2.0 从 LLM 迁回） |
| 存量房合同 | RULE | 规则层优先 |
| UNKNOWN | VLM | 未知文档走 VLM |

#### `rule_layer.py` — 规则提取层

分发到 4 个领域提取器：

```python
class RuleExtractionLayer:
    def __init__(self):
        self._personal_id = PersonalIdExtractor()
        self._household = HouseholdPropertyExtractor()
        self._financial = FinancialExtractor()
        self._agreement = AgreementExtractor()

    def extract(self, doc_info, key_list) -> ExtractionResult:
        # 根据 doc_type 分发到对应提取器
```

#### `vlm_layer.py` — VLM 视觉模型提取

- 支持模型：GLM-OCR（端口 8080）、Qwen2.5-VL-7B（端口 8082）
- 多页文档：逐页提取 + 字段合并（取第一个非空值）
- Prompt 模板：每个文档类型专用 Prompt（存储于 `prompt_templates.py`）

#### `vlm_fallback.py` — 字段级 VLM 兜底

```
规则层提取 → FieldValidator 校验 → 失败字段 → VLM 重新提取 → 合并结果
```

启用文档类型：户口本、结婚证、身份证。

#### `position_extractor.py` — 位置标注提取器

利用 PaddleOCR 坐标信息，基于空间位置关系提取字段：
- 解决列错位问题
- 解决标签+数据合并问题
- 解决长地址跨列问题

#### `service.py` — OCRService

```python
class OCRService:
    def __init__(self, config: Optional[OCRConfig] = None): ...
    def process_single(self, image_path, ocr_text="") -> Dict[str, Any]: ...
    def process_batch(self, images: List[Dict]) -> List[Dict]: ...
    def process_directory(self, dir_path) -> Dict[str, Any]: ...
    def run_ocr(self, image_path) -> str: ...
```

---

## 关键技术说明

### 1. ProcessingLayer 仅 RULE + VLM

**v2.0 决策**：LLM 层（PP-ChatOCRv4）处理购房合同、存量房合同、房产证时完全失败（提取字段数 0，耗时 197-316 秒/文档），已彻底移除。

当前架构：
- `ProcessingLayer.RULE` — 正则表达式 + 位置标注提取
- `ProcessingLayer.VLM` — 视觉语言模型提取
- 无 `ProcessingLayer.LLM`

### 2. SQLite WAL 模式 + thread-local 连接

```python
# task_manager.py 中的连接策略
_thread_local = threading.local()

def _get_connection(self) -> sqlite3.Connection:
    """每个线程独立连接，WAL 模式保证并发安全"""
    if not hasattr(_thread_local, "conn"):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn = conn
    return _thread_local.conn
```

### 3. 租户配额 — 纯 SQL JOIN

```sql
-- 不扫描文件系统，直接 SQL 查询
SELECT t.quota_limit, COUNT(tk.id) AS used
FROM tenants t
LEFT JOIN tasks tk ON tk.tenant_id = t.id
    AND tk.created_at > datetime('now', '-1 day')
WHERE t.api_key = ?
GROUP BY t.id
```

### 4. 工厂模式 create_app()

```python
# 依赖注入
app = create_app(
    ocr_service=OCRService(config),
    task_manager=TaskManager(db_path),
    authenticator=APIKeyAuthenticator(api_keys),
)
```

### 5. APIKeyAuthenticator 类

```python
# 认证器是类，非函数
class APIKeyAuthenticator:
    def __init__(self, api_keys: List[str]): ...
    def verify(self, token: str) -> bool: ...
```

### 6. OCRConfig 精简

```python
# v2.1.0：无 ClassificationServiceConfig、无 LLMServiceConfig、无 ThresholdsConfig
@dataclass
class OCRConfig:
    vlm_service: VLMServiceConfig
    qwen_vl_service: QwenVLServiceConfig
```

---

## 数据流

### 同步 OCR 请求

```
客户端 → POST /ocr/sync
       → APIKeyAuthenticator.verify(token)
       → OCRService.process_single(image_path)
           → Pipeline.process()
               → classifier.classify() → DocumentInfo
               → rule_layer.extract() 或 vlm_layer.extract()
               → vlm_fallback（可选）
           → ExtractionResult
       → APIResponse 返回
```

### 异步 OCR 请求

```
客户端 → POST /ocr/async
       → TaskManager.submit(task) → task_id
       → AsyncSubmitResponse(task_id)
       → 后台线程执行 OCRService.process_single()
       → TaskManager.update_status(task_id, result)

客户端 → GET /task/{task_id}
       → TaskManager.get_status(task_id)
       → TaskStatusResponse 返回
```

### 租户配额查询

```
客户端 → GET /quota
       → APIKeyAuthenticator.verify(token)
       → TaskManager.get_quota(api_key)
           → SQL JOIN 查询（tenants + tasks）
       → QuotaResponse 返回
```

---

## 部署与配置

### VLM 服务端口

| 端口 | 模型 | 用途 |
|------|------|------|
| 8080 | GLM-OCR | 默认 VLM 提取 |
| 8082 | Qwen2.5-VL-7B | 备选 VLM 提取（理解能力更强） |

### 启动命令

```bash
# Qwen2.5-VL-7B
cd models-OCR/Qwen2.5-VL-7B && llama-server \
  --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \
  --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \
  --host 0.0.0.0 --port 8082 --ctx-size 8192

# API 服务
uvicorn ocr_api.ocr.server:create_app --factory --host 0.0.0.0 --port 8000
```

### 依赖包

- `fastapi` — Web 框架
- `paddleocr` — OCR 引擎（位置标注提取）
- `pillow` — 图像处理
- `requests` — HTTP 请求
- `pydantic` — 数据验证
- `sqlite3` — 任务队列（标准库）

---

## 附录

### 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-06 | 初始三层架构：RULE + LLM + VLM |
| v2.0 | 2026-07-05 | 移除 LLM 层，简化为 RULE + VLM |
| v2.1.0 | 2026-07-09 | API 服务层独立（FastAPI）、租户配额、工厂模式、多页独立分类 |

### 相关文档

- `docs/OCR_API接口文档.md` — API 接口详细说明
- `docs/multi_page_vlm_extraction_plan.md` — 多页 VLM 提取方案
- `docs/扩展指南_新增证件类型.md` — 新增文档类型指南
- `docs/history/` — 历史文档归档（含已废弃的 LLM 层、VLM 分类器文档）

---

*最后更新: 2026-07-09 | 版本: v2.1.0*
