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
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
~~~

或者直接运行：

~~~powershell
.\start.ps1
~~~

### 5. 打开页面

浏览器访问：

~~~text
http://127.0.0.1:8000
~~~

## API

### 工作票业务能力

结构化识别完成后，系统除原始 JSON 外还会生成：

- 标准工作票档案（票号、地点、负责人、时间、作业内容、安全措施、风险点等）
- 兼容旧 ticket 项目的 `entities` 与 `relationships`
- 按工作票号保存到 `storage/tickets/`
- 可通过受保护接口同步到智能安监工地、查询档案和生成违章关联报告

受保护接口必须设置 `.env` 中的 `HAZARD_INTEGRATION_TOKEN`，并携带请求头：

```text
X-Integration-Token: 与 HAZARD_INTEGRATION_TOKEN 相同的值
```

- `POST /api/v1/parse_ticket`：兼容旧项目的识别入口，可带查询参数 `enable_hazard_sync=true&hazard_site_name=测试变电站`
- `GET /api/v1/tickets/{ticket_no}`：读取已归档工作票
- `POST /api/v1/apply_ticket_to_site`：将已归档工作票绑定到安监工地
- `POST /api/v1/generate_violation_report`：结合工作票与摄像头违章结果生成报告

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
