# Strategic Signal Scanner

为 AI 造物社区建设的 Google Cloud 技术研究流水线：收集材料、规范化与去重，
调用模型评分，输出供人工研究与选题使用的 JSON。

[项目叙述](docs/PROJECT_CONTEXT.zh-CN.md) | [English](README.md) |
[Google Cloud 工程案例](docs/GOOGLE_CLOUD_CASE_STUDY.md) |
[技术指南](docs/TECHNICAL_GUIDE.md) | [可选模型接口](docs/OPTIONAL_ADAPTERS.md)

## 公开技术主线

```text
Cloud Build -> Artifact Registry -> Cloud Run Jobs
Cloud Scheduler -- OAuth --> Run Jobs :run API
运行服务账号 -> ADC/IAM -> Gemini 与私有 Cloud Storage

恢复采集状态 -> 采集 -> 规范化与去重 -> raw JSON
-> Gemini Vertex SDK -> scored JSON 与选中候选
-> 将 raw/scored/state JSON 保存到私有 bucket
-> 人工研究与后续编辑
```

来源 URL、标题、日期、摘要和评分保留在 JSON 中。公开代码聚焦采集、去重、
模型集成与状态存储；内容呈现和分发由后续流程承接。

## 运行入口

需要 Python 3.11 或更高版本。查看帮助不需要账号或网络：

```sh
python3 -B tools/capture_and_score.py --help
python3 -B tools/score_raw_rss.py --help
```

真实运行时安装 requirements.txt，配置项目、区域、模型和操作者自己的输入。
采集、评分和部署命令见[技术指南](docs/TECHNICAL_GUIDE.md)。真实请求可能产生费用，
必须显式选择网络采集和模型模式；默认评分为本地 mock。

## 模块

- 采集与规范化：通用官方来源配置，RSS/Atom、网页、YouTube feed 和 JSON 适配器。
- 去重与状态：规范化 URL、标题/内容键、刷新窗口和持久化采集记录。
- 模型评分：Google Gen AI SDK、Vertex/ADC、瞬时错误重试和元数据保护。
- JSON 输出：原始记录、评分结果、摘要、来源链接及阈值筛选后的候选。
- 云端编排：Cloud Run Jobs 入口、私有 GCS 状态恢复与 JSON 上传白名单。
- 可选接口：DeepSeek、Gemini API-key 模式与独立 SMTP 工具。

## 配置与部署

Vertex 主路径显式设置 GEMINI_BACKEND=vertex、项目、区域和模型，通过运行服务账号
获取 ADC，不需要模型 API key。PRIVATE_ARTIFACT_BUCKET 可选启用私有持久化，
仅接收 raw/scored JSON 与 state.json。Job 不枚举下载全部历史结果。

容器默认只显示帮助并退出；真实 Job 需要覆盖入口。OUTPUT_DIR 应为专用工作目录，
每轮清理上一轮 raw/scored 文件并保留状态。远端历史不自动删除，多执行需要外部互斥。

## 权利说明

原创与新增部分未授予使用或商用许可，商业使用需要事先书面授权；既有上游 MIT
部分的授权不变。见 [RIGHTS.md](RIGHTS.md) 与[上游声明](LICENSE-MIT-UPSTREAM.txt)。
