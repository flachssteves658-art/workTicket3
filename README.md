# 工作票智能识别台

这是一个基于 PaddleOCR PPStructureV3 + 大语言模型 的工作票识别项目。

它包含两个功能模块：

1. 结构化识别
   - 一次可选择最多 20 个工作票图片或 PDF，按队列逐个处理；
   - 后端调用 PaddleOCR PPStructureV3 做版面、表格、文字识别；
   - 保存 PPStructureV3 的 Markdown / JSON 原始结果；
   - 再交给大语言模型整理成固定 JSON。

2. 图片直传大模型
   - 一次可选择最多 20 张图片，按队列逐个处理；
   - 不经过 PPStructureV3；
   - 直接把图片发给多模态大模型；
   - 每张图片独立显示处理状态和模型返回结果，单个任务失败不会中断后续任务。

## 项目结构

~~~text
.
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── config.py              # 配置
│   ├── llm_client.py          # OpenAI-compatible 大模型调用
│   └── ppstructure_v3.py      # PPStructureV3 调用与结果收集
├── web/
│   ├── index.html             # 前端页面
│   ├── styles.css             # 视觉样式
│   └── app.js                 # 前端交互
├── storage/
│   ├── uploads/               # 上传文件
│   └── outputs/               # OCR / LLM 输出结果
├── requirements.txt
├── .env.example
├── start.ps1
└── README.md
~~~

## 启动步骤

### 1. 创建虚拟环境

Windows PowerShell：

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
~~~

### 2. 安装依赖

~~~powershell
pip install -r requirements.txt
~~~

如果当前环境还没有 PaddleOCR 3.x，需要额外安装 PaddlePaddle 和 PaddleOCR。

CPU 环境可以参考：

~~~powershell
pip install paddlepaddle
pip install "paddleocr>=3.0.0"
~~~

如果你使用 GPU，请根据自己的 CUDA 版本安装对应的 PaddlePaddle 包。

### 3. 配置大模型

复制配置文件：

~~~powershell
Copy-Item .env.example .env
~~~

然后编辑 .env：

~~~env
LLM_API_KEY=你的_API_Key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini
~~~

说明：

- LLM_MODEL 用于 PPStructureV3 结果整理成 JSON；
- VISION_MODEL 用于图片直接发送给多模态大模型；
- 后端使用 OpenAI-compatible /chat/completions 接口，所以也可以接入兼容 OpenAI 格式的内网模型服务。

### 4. 启动项目

~~~powershell
uvicorn app.main:app --host 127.0.0.1 --port 8880 --reload
~~~

或者直接运行：

~~~powershell
.\start.ps1
~~~

### 5. 打开页面

浏览器访问：

~~~text
http://127.0.0.1:8880
~~~

不要双击 `web/index.html` 使用 `file:///...` 打开；静态页面必须通过上述
HTTP 地址访问，才能调用后端接口。

## API

### 工作票业务能力

结构化识别完成后，系统除原始 JSON 外还会生成：

- 标准工作票档案（票号、地点、负责人、时间、作业内容、安全措施、风险点等）
- 兼容旧 ticket 项目的 `entities` 与 `relationships`
- 按工作票号保存到 `storage/tickets/`
- 可通过受保护接口同步到智能安监工地、查询档案和生成违章关联报告
- 可导入设备清单（`.xls`）和摄像头清单（`.xlsx`），形成“工作票→设备台账→摄像头候选→AI检测任务”闭环

### 设备与摄像头闭环

1. 在页面“台账配置”中导入设备清单和摄像头清单。
2. 上传工作票，系统自动从结构化内容中识别站点和设备名称。
3. 用所属电站、设备名称、运行编号、调度命名、所属间隔和功能位置编码匹配设备台账。
4. 再用站点、设备/间隔、安装位置和监控区域匹配摄像头，并输出置信度和匹配原因。
5. 高置信度结果可自动推荐，其余结果必须人工确认。
6. 将候选摄像头绑定到智能安监中同站点的 `stream_configs` 视频流（RTSP凭据仍只保存在智能安监数据库中）。
7. 确认后在 MySQL 持久化AI检测任务及任务-摄像头-视频流快照。
8. 任务会按时间进入 `scheduled`、`active` 或 `expired` 状态；只有排期中或执行中的任务会更新被确认的视频流。实时预览不受影响，AI推理仅在工作票时间窗内执行。

台账原始文件不会复制进Git。页面读取Excel后通过受保护接口写入智能安监项目现有的 MySQL；运行期的设备查询、摄像头匹配、人工确认结果全部来自数据库，不再读取本地目录JSON。

数据库由智能安监项目的8005数据库管理服务统一持有，`workTicket3` 不保存 MySQL 账号。两个项目需使用同一个集成令牌：

```text
workTicket3: HAZARD_INTEGRATION_TOKEN
智能安监项目: INTEGRATION_TOKEN
```

受保护接口必须设置 `.env` 中的 `HAZARD_INTEGRATION_TOKEN`，并携带请求头：

```text
X-Integration-Token: 与 HAZARD_INTEGRATION_TOKEN 相同的值
```

- `POST /api/v1/parse_ticket`：兼容旧项目的识别入口，可带查询参数 `enable_hazard_sync=true&hazard_site_name=测试变电站`
- `GET /api/v1/tickets/{ticket_no}`：读取已归档工作票
- `POST /api/v1/apply_ticket_to_site`：将已归档工作票绑定到安监工地
- `POST /api/v1/generate_violation_report`：结合工作票与摄像头违章结果生成报告
- `GET /api/catalog/status`：查看设备与摄像头目录状态
- `POST /api/catalog/import`：导入两份台账
- `POST /api/v1/tickets/{ticket_no}/match-assets`：重新执行设备与摄像头匹配
- `GET /api/v1/tickets/{ticket_no}/asset-matches`：读取匹配结果
- `GET /api/v1/stream-options`：读取智能安监中可绑定的视频流（不返回RTSP地址）
- `POST /api/v1/cameras/bind-streams`：将摄像头编号绑定到同站点视频流
- `POST /api/v1/tickets/{ticket_no}/confirm-cameras`：人工确认摄像头并生成AI检测任务
- `GET /api/v1/tickets/{ticket_no}/detection-task`：读取已持久化的AI检测任务
- `POST /api/v1/tickets/{ticket_no}/cancel-detection-task`：取消任务并解除对应视频流的工作票时间窗

### 健康检查

~~~http
GET /api/health
~~~

### 结构化识别

~~~http
POST /api/recognize-structure
Content-Type: multipart/form-data

file=@工作票.pdf
~~~

流程：

~~~text
上传文件
  ↓
PPStructureV3 识别
  ↓
保存 Markdown / JSON
  ↓
大模型整理
  ↓
返回结构化 JSON
~~~

### 图片直传大模型

~~~http
POST /api/direct-vision
Content-Type: multipart/form-data

file=@工作票图片.jpg
prompt=请识别图片内容
~~~

该接口不做任何结果约束，直接返回大模型原始输出。

## 输出位置

上传文件会保存在：

~~~text
storage/uploads/
~~~

PPStructureV3 和大模型结果会保存在：

~~~text
storage/outputs/
~~~

每次结构化识别会生成类似：

~~~text
storage/outputs/ticket_xxxxxxxx/
├── ppstructure_json/
├── ppstructure_markdown/
├── visual/
└── llm_result.json
~~~

## 注意事项

1. 第一次运行 PPStructureV3 可能会下载模型，耗时较长。
2. 如果网络受限，请提前准备好 PaddleOCR 模型缓存。
3. 如果大模型不支持图片输入，图片直传大模型模块会失败，需要换成支持视觉的模型。
4. 结构化识别依赖 OCR 质量，大模型不会被要求猜测缺失字段。
5. 如果 PPStructureV3 无法导入，请确认 PaddleOCR 版本是 3.x。
