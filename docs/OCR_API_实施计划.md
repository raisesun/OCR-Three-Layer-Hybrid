# OCR API 服务 - 实施计划 v2.0

## 更新日期: 2026-07-05

---

## 一、用户决策汇总

| 决策项 | 选择 | 备注 |
|--------|------|------|
| **部署方式** | 1台服务器，直接部署 | 不用Docker，快速上线 |
| **API Key分级** | 初期单一级别 | 分级记入待办，下一版实现 |
| **自助申请** | 下一版增加 | 记入待办 |
| **PDF处理** | 分类处理（推荐方案B） | 文字PDF直接提取，扫描件转图片OCR |
| **接口模式** | 仅异步接口 | 内部同步处理，对外只暴露异步 |
| **监控告警** | 邮件 + Dashboard | 钉钉/企业微信下一版 |

---

## 二、待办事项清单

### 2.1 第一版（MVP）

- [ ] **基础架构**
  - [ ] FastAPI应用框架搭建
  - [ ] 异步任务队列（数据库任务表）
  - [ ] 临时文件管理（自动清理）
  - [ ] 健康检查端点

- [ ] **核心接口**
  - [ ] POST /api/v1/ocr/submit - 提交任务
  - [ ] GET /api/v1/task/{id} - 查询任务
  - [ ] POST /api/v1/task/{id}/cancel - 取消任务
  - [ ] GET /api/v1/tasks - 列出任务

- [ ] **PDF处理**
  - [ ] 文字PDF文本提取（PyMuPDF）
  - [ ] 扫描件PDF转图片（300 DPI）
  - [ ] PDF类型自动判断

- [ ] **鉴权**
  - [ ] API Key生成和管理
  - [ ] Bearer Token验证
  - [ ] 基础限流（按API Key）

- [ ] **监控**
  - [ ] 邮件告警配置
  - [ ] 基础Dashboard（任务数、成功率、响应时间）
  - [ ] 结构化日志

- [ ] **部署**
  - [ ] 生产服务器配置
  - [ ] Nginx反向代理
  - [ ] Systemd服务管理
  - [ ] HTTPS证书配置

### 2.2 第二版（增强）

- [ ] **API Key分级**
  - [ ] 基础版/标准版/企业版/内部版
  - [ ] 不同配额限制
  - [ ] 管理后台

- [ ] **自助申请**
  - [ ] API Key在线申请页面
  - [ ] 自动审批流程（或人工审批）
  - [ ] 用量查询页面

- [ ] **监控增强**
  - [ ] 钉钉告警
  - [ ] 企业微信告警
  - [ ] Prometheus + Grafana完整Dashboard
  - [ ] 告警规则配置

- [ ] **功能增强**
  - [ ] Webhook回调（任务完成通知）
  - [ ] 批量任务优先级
  - [ ] 结果缓存（相同图片不重复处理）

- [ ] **扩展准备**
  - [ ] Docker化（为后续扩展做准备）
  - [ ] 数据库迁移脚本（SQLite → PostgreSQL）
  - [ ] 水平扩展文档

### 2.3 第三版（公网）

- [ ] **公网部署**
  - [ ] 云服务商选择（阿里云/腾讯云）
  - [ ] 负载均衡配置
  - [ ] CDN配置（静态资源）
  - [ ] WAF配置（Web应用防火墙）

- [ ] **安全增强**
  - [ ] OAuth2支持
  - [ ] 频率限制增强
  - [ ] 请求签名验证
  - [ ] IP白名单

- [ ] **高可用**
  - [ ] 多实例部署
  - [ ] 数据库主从
  - [ ] Redis缓存层
  - [ ] 自动扩缩容

---

## 三、技术架构（第一版）

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        客户端/调用方                          │
└────────────────────────────────────────────────────────────┘
                        │ HTTPS
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      Nginx (反向代理)                         │
│  - SSL终止                                                    │
│  - 请求限流 (100 req/s)                                       │
│  - 静态文件（API文档）                                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 应用                               │
│  ─────────────────────────────────────────────────────   │
│  │  认证中间件 (API Key验证)                              │   │
│  │  限流中间件 (按API Key)                                │   │
│  │                                                       │   │
│  │  路由层                                                │   │
│  │  ├── POST /api/v1/ocr/submit   (提交任务)             │   │
│  │  ├── GET  /api/v1/task/{id}    (查询任务)             │   │
│  │  ├── POST /api/v1/task/{id}/cancel (取消任务)         │   │
│  │  ├── GET  /api/v1/tasks        (列出任务)             │   │
│  │  └── GET  /health              (健康检查)             │   │
│  │                                                       │   │
│  │  业务层                                                │   │
│  │  ├── 文件处理 (临时文件 + PDF解析)                      │   │
│  │  ├── 任务管理 (数据库任务表)                            │   │
│  │  ── OCR处理 (调用现有pipeline - 内部同步)             │   │
│  │                                                       │   │
│  │  后台任务处理器                                         │   │
│  │  └─ 异步处理队列中的任务                                 │   │
│  │     └─ 调用 OCRService.process_single()               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  单实例部署                                                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
─────────────────────────────────────────────────────────────┐
│                      依赖服务                                 │
│  ──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  PP-OCRv6    │  │  VLM Service │  │   SQLite     │      │
│  │  (本地)      │  │  (本地)      │  │  (任务存储)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈

| 组件 | 技术选择 | 版本 | 理由 |
|------|----------|------|------|
| Web框架 | FastAPI | 0.100+ | 异步支持、自动文档 |
| 反向代理 | Nginx | 1.24+ | SSL、限流 |
| 数据库 | SQLite | 3.40+ | 轻量、无需部署 |
| PDF处理 | PyMuPDF | 1.23+ | 文字提取+转图片 |
| 任务处理 | APScheduler | 3.10+ | 后台任务调度 |
| 邮件告警 | smtplib | 内置 | 标准库，无需依赖 |
| 监控 | Prometheus Client | 0.17+ | 指标采集 |

### 3.3 目录结构

```
OCR-Three-Layer-Hybrid/
├── api/                          # API服务（新增）
│   ├── __init__.py
│   ├── main.py                   # FastAPI应用入口
│   ├── config.py                 # API配置
│   ├── auth.py                   # 认证中间件
│   ├── rate_limiter.py           # 限流中间件
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ocr.py                # OCR接口
│   │   ├── task.py               # 任务接口
│   │   └── health.py             # 健康检查
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_handler.py       # 文件处理
│   │   ├── pdf_handler.py        # PDF处理
│   │   ├── task_manager.py       # 任务管理
│   │   └── ocr_processor.py      # OCR处理（调用现有pipeline）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py           # 数据库模型
│   │   └── task.py               # 任务模型
│   └── utils/
│       ├── __init__.py
│       ├── email_alert.py        # 邮件告警
│       ── metrics.py            # 指标采集
── src/                          # 现有核心代码
├── scripts/                      # 脚本
├── docs/                         # 文档
└── analysis/                     # 分析文档
```

---

## 四、核心设计

### 4.1 任务状态机

```
                    ┌─────────────┐
                    │   pending   │
                    └──────┬──────┘
                           │ 开始处理
                           ▼
                    ┌─────────────┐
        ┌───────────│ processing  │───────────┐
        │           └──────┬──────┘           │
        │                  │ 完成              │ 失败
        │                  ▼                   ▼
        │           ┌─────────────┐     ┌─────────────┐
        │           │ completed   │     │   failed    │
        │           └─────────────┘     └─────────────┘
        │                  │
        │                  │ 取消
        │                  ▼
        │           ┌─────────────┐
        └───────────│  cancelled  │
                    └─────────────┘
```

### 4.2 任务表设计

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,           -- 任务ID (task_20260705_abc123)
    api_key_id INTEGER,            -- API Key ID
    status TEXT NOT NULL,          -- pending/processing/completed/failed/cancelled
    priority TEXT DEFAULT 'normal',-- normal/urgent
    
    -- 文件信息
    file_count INTEGER,            -- 文件数量
    total_size_bytes INTEGER,      -- 总大小
    
    -- 进度
    processed INTEGER DEFAULT 0,   -- 已处理数量
    progress INTEGER DEFAULT 0,    -- 进度百分比 0-100
    
    -- 时间
    submitted_at TIMESTAMP,        -- 提交时间
    started_at TIMESTAMP,          -- 开始时间
    completed_at TIMESTAMP,        -- 完成时间
    
    -- 结果
    result TEXT,                   -- JSON结果（完成后存储）
    error_message TEXT,            -- 错误信息（失败时）
    
    -- 回调
    callback_url TEXT,             -- 回调URL
    callback_sent BOOLEAN DEFAULT FALSE, -- 回调是否已发送
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_api_key ON tasks(api_key_id);
CREATE INDEX idx_tasks_submitted ON tasks(submitted_at);
```

### 4.3 文件处理流程

```
1. 接收文件上传
   └─ 保存到临时目录: /tmp/ocr_tasks/{task_id}/

2. PDF类型判断
   ├─ 文字PDF: 直接提取文本 → 跳过OCR
   └─ 扫描件PDF: 转为图片（300 DPI）→ 走OCR

3. 逐文件处理
   ├─ 调用 OCRService.process_single()
   ├─ 更新进度: processed++, progress = processed/total*100
   └─ 保存结果到内存

4. 完成处理
   ├─ 合并所有结果
   ├─ 更新任务状态: completed
   ├─ 存储结果到数据库
   ├─ 清理临时文件
   └─ 发送回调（如果有callback_url）
```

### 4.4 后台任务处理器

```python
# 使用 APScheduler 定时检查待处理任务
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('interval', seconds=5)
def process_pending_tasks():
    """处理待处理的任务"""
    # 1. 查询 pending 状态的任务（按优先级和提交时间排序）
    # 2. 更新状态为 processing
    # 3. 逐文件处理
    # 4. 更新状态为 completed/failed
    # 5. 发送回调通知

scheduler.start()
```

---

## 五、部署方案（第一版）

### 5.1 服务器配置

| 项目 | 配置 |
|------|------|
| CPU | 16核 |
| 内存 | 64GB |
| 磁盘 | 200GB SSD |
| 网络 | 千兆以太网 |
| OS | Ubuntu 22.04 LTS |

### 5.2 部署步骤

```bash
# 1. 系统更新
sudo apt update && sudo apt upgrade -y

# 2. 安装Python 3.11
sudo apt install python3.11 python3.11-venv python3.11-dev -y

# 3. 安装Nginx
sudo apt install nginx -y

# 4. 创建应用目录
sudo mkdir -p /opt/ocr-api
sudo chown $USER:$USER /opt/ocr-api

# 5. 部署代码
cd /opt/ocr-api
git clone <repo_url> .
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 6. 配置Systemd服务
sudo nano /etc/systemd/system/ocr-api.service

# 7. 配置Nginx
sudo nano /etc/nginx/sites-available/ocr-api

# 8. 配置SSL（Let's Encrypt）
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d ocr.api.example.com

# 9. 启动服务
sudo systemctl enable ocr-api
sudo systemctl start ocr-api
sudo systemctl reload nginx
```

### 5.3 Systemd服务配置

```ini
[Unit]
Description=OCR API Service
After=network.target

[Service]
Type=simple
User=ocr
WorkingDirectory=/opt/ocr-api
ExecStart=/opt/ocr-api/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

# 环境变量
Environment=OCR_API_ENV=production
Environment=OCR_API_DB_PATH=/opt/ocr-api/data/tasks.db
Environment=OCR_API_UPLOAD_DIR=/tmp/ocr-uploads
Environment=OCR_API_LOG_LEVEL=INFO

[Install]
WantedBy=multi-user.target
```

### 5.4 Nginx配置

```nginx
server {
    listen 80;
    server_name ocr.api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ocr.api.example.com;

    ssl_certificate /etc/letsencrypt/live/ocr.api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ocr.api.example.com/privkey.pem;

    # 限流配置
    limit_req_zone $binary_remote_addr zone=ocr_api:10m rate=100r/s;

    client_max_body_size 100M;  # 最大上传100MB

    location / {
        limit_req zone=ocr_api burst=50 nodelay;
        
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 长超时（支持大文件上传）
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 静态文件（API文档）
    location /docs {
        alias /opt/ocr-api/docs/;
        index index.html;
    }
}
```

---

## 六、监控方案（第一版）

### 6.1 邮件告警配置

```python
# api/utils/email_alert.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailAlerter:
    def __init__(self, smtp_host, smtp_port, username, password, recipients):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.recipients = recipients
    
    def send_alert(self, subject, body):
        msg = MIMEMultipart()
        msg['From'] = self.username
        msg['To'] = ', '.join(self.recipients)
        msg['Subject'] = f"[OCR API] {subject}"
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

# 告警触发条件
ALERT_RULES = {
    'high_error_rate': {'threshold': 0.05, 'window': 300},  # 5%错误率，5分钟窗口
    'long_queue': {'threshold': 50, 'window': 600},         # 队列>50，10分钟
    'slow_response': {'threshold': 60, 'window': 300},      # P99>60秒，5分钟
}
```

### 6.2 Dashboard指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `api_requests_total` | Counter | 总请求数 |
| `api_requests_failed_total` | Counter | 失败请求数 |
| `task_submitted_total` | Counter | 提交任务数 |
| `task_completed_total` | Counter | 完成任务数 |
| `task_failed_total` | Counter | 失败任务数 |
| `task_processing_duration_seconds` | Histogram | 任务处理时间 |
| `queue_length` | Gauge | 当前队列长度 |
| `active_connections` | Gauge | 当前连接数 |

### 6.3 日志格式

```json
{
  "timestamp": "2026-07-05T10:30:00Z",
  "level": "INFO",
  "logger": "ocr_api.task",
  "message": "Task completed",
  "task_id": "task_abc123",
  "api_key_id": 123,
  "file_count": 10,
  "duration_seconds": 45.2,
  "status": "completed"
}
```

---

## 七、时间表

| 阶段 | 工作内容 | 预计时间 |
|------|----------|----------|
| **第1周** | 基础架构 + 核心接口 | 5天 |
| **第2周** | PDF处理 + 鉴权 | 5天 |
| **第3周** | 监控 + 部署 | 5天 |
| **第4周** | 测试 + 优化 | 5天 |

**总计**: 4周（20个工作日）

---

## 八、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| VLM服务不稳定 | 中 | 高 | 熔断降级到规则层 |
| 单点故障 | 高 | 高 | 快速切换到备用服务器 |
| 磁盘空间不足 | 中 | 中 | 定期清理临时文件 |
| 内存泄漏 | 低 | 高 | 定期重启服务 |
| 并发超预期 | 低 | 高 | 限流 + 队列缓冲 |

---

## 九、验收标准

### 9.1 功能验收

- [ ] 可以提交异步任务
- [ ] 可以查询任务状态
- [ ] 可以取消任务
- [ ] 支持图片（JPG/PNG/BMP）
- [ ] 支持PDF（文字+扫描件）
- [ ] API Key认证有效
- [ ] 限流功能正常
- [ ] 邮件告警正常

### 9.2 性能验收

- [ ] 任务提交响应时间 < 1秒
- [ ] 单张图片处理时间 < 10秒（规则层）
- [ ] 单张图片处理时间 < 120秒（VLM层）
- [ ] 支持100个并发任务
- [ ] 7x24小时稳定运行

### 9.3 安全验收

- [ ] HTTPS加密传输
- [ ] API Key验证有效
- [ ] 文件上传限制有效
- [ ] 临时文件自动清理
- [ ] 敏感信息不泄露

---

## 十、后续演进

### 10.1 短期（1-3个月）
- API Key分级
- 自助申请页面
- 钉钉/企业微信告警
- 完整Dashboard

### 10.2 中期（3-6个月）
- Docker化
- 多实例部署
- 数据库迁移到PostgreSQL
- Redis缓存层

### 10.3 长期（6-12个月）
- 公网部署
- Kubernetes集群
- 自动扩缩容
- OAuth2支持
- 多区域部署
