# Technical Guide

本指南说明公开 Scanner 的采集、去重、模型调用、JSON 输出与 GCS 持久化。
架构背景见 [Google Cloud 工程案例](GOOGLE_CLOUD_CASE_STUDY.md)。

## Workflow

```text
sources.py -> rss_capture.py -> fetcher.py -> state.py
          -> raw JSON -> score_raw_rss.py -> signal_replay.py
          -> scored JSON and selected candidates
cloudrun_job.py -> restore state -> capture/score -> private GCS upload
```

Cloud Scheduler 使用 OAuth 调用 Run Jobs API；Cloud Run 运行账号通过 ADC
访问 Gemini 和 Cloud Storage。Cloud Build 与 Artifact Registry 承担镜像交付。

## Entry Points

Python 3.11+。帮助命令不会访问网络：

```sh
python3 -B tools/capture_and_score.py --help
python3 -B tools/score_raw_rss.py --help
python3 -B tools/signal_replay.py --help
```

真实请求需要先安装依赖并配置 ADC；Cloud Run 使用关联运行服务账号，本地使用
操作者授权的开发凭据。不把静态服务账号 key 复制到镜像。

```sh
python3 -m pip install -r requirements.txt
export SCANNER_LOAD_ENV=0
export GEMINI_BACKEND=vertex
export GEMINI_PROJECT='<google-cloud-project-id>'
export GEMINI_LOCATION='<supported-model-location>'
export GEMINI_MODEL='<supported-model-id>'
STATE_PATH=/tmp/scanner-work/state.json \
python3 -B tools/capture_and_score.py --allow-network \
  --group official --items-per-feed 1 --max-articles 3 \
  --output-dir /tmp/scanner-work --score-mode gemini \
  --model "$GEMINI_MODEL" --retry-attempts 3 --min-score 4
```

命令访问来源并调用模型，可能产生费用。只有具备处理权限的材料才应发送给模型。
对已有原始 JSON 单独评分：

```sh
python3 -B tools/score_raw_rss.py /tmp/scanner-work/raw_YYYY-MM-DD.json \
  --mode gemini --retry-attempts 3 --min-score 4
```

raw 文件必须已存在并包含文章对象列表。默认 mock 不发出模型请求，但网络采集仍
需要显式授权。replay 的 --samples 参数要求操作者提供自己的输入文件或目录。

## Capture and Deduplication

来源配置包含名称、类型、URL、可选层级和刷新窗口。采集适配器支持 RSS/Atom、
选定网页、YouTube feed 和 HTTP/JSON。网页提取不执行 JavaScript，不绕过登录。
官方来源组是通用配置，可以替换成自己的授权来源。

state.py 保存规范化 URL、标题与内容哈希、来源刷新时间。URL 去掉常见追踪参数；
标题和内容键用于发现重复材料，不等于语义聚类。损坏状态会明确失败。
状态采用临时文件替换，但没有跨进程锁。--ignore-state 适合受控重放而非常规运行。

## JSON Contract

| 对象 | 内容 |
| --- | --- |
| 原始条目 | title、source、url、date/published、summary/content、fetched_at 和适配器字段 |
| 评分结果 analysis | 原始标题/来源/日期/URL、tier、signal_type、relevance_score、relevance_reason、summary_zh、key_signal、action_hint |
| scored 文件 | source_file、scored_at、mode、model、count、items、high_signal_items、high_signal_count |
| state.json | 去重键、来源刷新记录与保存时间 |

评分保留原始采集字段；模型输出不能改写来源元数据。relevance_score 限定为 0–5，
tier 限定为 1–4。候选按 --min-score 筛选并按分数降序；空列表意味着没有入选候选。
模型只分析提供的文本，不调用搜索工具，评分不构成事实核查或发布批准。
文件日期用于区分运行结果，没有报告页面或日期索引。

## Gemini Through Vertex and ADC

实现位于 [signal_replay.py](../tools/signal_replay.py)，主路径显式设置
GEMINI_BACKEND=vertex。项目、位置和模型由环境或 CLI 配置。

```python
client = genai.Client(
    vertexai=True,
    project=project,
    location=location,
    http_options=http_options,
)
response = client.models.generate_content(model=model, contents=prompt)
```

上述摘录合并展示客户端构造与调用，两者在实际代码中分别位于客户端初始化和重试循环。
运行账号需要相应模型权限，例如 roles/aiplatform.user。ADC 由运行环境提供，
Vertex 不需要 API key，也不会回退到 API-key REST 请求。

请求有 60 秒单次超时和有限指数退避；429、瞬时服务器错误和超时可重试。
非重试错误与无法解析的 JSON 直接失败，不静默改用 mock。响应规范化不是完整
Schema 验证或自动事实核查。通用提示词见 [system_instruction.md](../tools/system_instruction.md)。

## Cloud Run Job and Private Storage

Job 依次验证配置、创建专用工作目录、恢复 state.json、运行采集/评分，再上传
raw/scored JSON 与 state.json。任何采集/评分失败都会停止，不继续上传。
状态路径可显式配置，子进程继承相同位置。缺少远端 state 时从空状态开始，
权限或传输错误会中止。Job 不枚举和下载全部历史评分对象。

上传器仅接受普通文件，并限定 state.json、raw_*.json、scored_*.json；跳过符号链接、
其他 JSON 和无关文件。上传目标必须是配置的 PRIVATE_ARTIFACT_BUCKET。
PRIVATE_ARTIFACT_PREFIX 默认 signal-private。对象不自动公开，管理员需设置私有策略。
原始资料和评分结果属于运行数据，不应提交到源码仓库。

容器文件系统是工作空间。OUTPUT_DIR 默认 /tmp/artifacts/rss，必须专用；每轮会清理
其中已有 raw/scored JSON，但保留 state。远端历史没有自动保留期限，同日文件可替换。
没有 GCS 版本前置条件或分布式锁，多执行需外部互斥。状态先于模型评分推进，
评分失败可从保留 raw 文件重跑；不要盲目重新采集。

## Deployment Reference

以下命令是会改变资源并可能产生费用的操作参考。需事先准备项目、运行服务账号、
私有 bucket 和 Artifact Registry 仓库，并开启对应 API。在干净的仓库目录执行。

```sh
export PROJECT_ID='<google-cloud-project-id>'
export REGION='<cloud-run-region>'
export REPOSITORY='<artifact-registry-repository>'
export JOB_NAME='<cloud-run-job-name>'
export RUN_SA_EMAIL='<runtime-service-account-email>'
export PRIVATE_BUCKET_NAME='<private-bucket-name>'
export MODEL_LOCATION='<supported-model-location>'
export MODEL_ID='<supported-model-id>'
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/scanner:reviewed"
gcloud builds submit --project "$PROJECT_ID" --tag "$IMAGE" .
gcloud storage buckets add-iam-policy-binding "gs://$PRIVATE_BUCKET_NAME" \
  --member="serviceAccount:$RUN_SA_EMAIL" --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUN_SA_EMAIL" --role=roles/aiplatform.user
gcloud run jobs deploy "$JOB_NAME" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE" --service-account "$RUN_SA_EMAIL" \
  --command python --args=-B,tools/cloudrun_job.py \
  --tasks 1 --parallelism 1 --max-retries 0 --task-timeout 3600s \
  --set-env-vars="ALLOW_NETWORK=true,SCORE_MODE=gemini,GEMINI_BACKEND=vertex,GEMINI_PROJECT=$PROJECT_ID,GEMINI_LOCATION=$MODEL_LOCATION,GEMINI_MODEL=$MODEL_ID,RUN_GROUP=official,PRIVATE_ARTIFACT_BUCKET=$PRIVATE_BUCKET_NAME,OUTPUT_DIR=/tmp/artifacts/rss"
```

存储角色限定在目标 bucket；可按实际需要改为更小的自定义权限。
构建身份需要目标仓库写入与日志权限；部署身份需要部署及运行账号 actAs 权限。
同项目镜像由 Cloud Run 平台服务代理读取，不要混淆构建、部署和运行身份。
容器默认只显示帮助，真实 Job 必须覆盖入口；上面已经显式覆盖。

Scheduler 使用独立触发账号，授予目标 Job 的 Run Invoker 权限：

```sh
export SCHEDULER_NAME='<scheduler-job-name>'
export SCHEDULER_SA_EMAIL='<scheduler-service-account-email>'
gcloud run jobs add-iam-policy-binding "$JOB_NAME" --project "$PROJECT_ID" \
  --region "$REGION" --member="serviceAccount:$SCHEDULER_SA_EMAIL" --role=roles/run.invoker
gcloud scheduler jobs create http "$SCHEDULER_NAME" --project "$PROJECT_ID" \
  --location "$REGION" --schedule="0 8 * * *" --time-zone="Etc/UTC" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$JOB_NAME:run" \
  --http-method=POST --headers="Content-Type=application/json" --message-body="{}" \
  --oauth-service-account-email="$SCHEDULER_SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

触发成功不是批处理完成。单次任务 parallelism=1 也不阻止两个执行重叠。
需要另配完成状态监控、运行互斥、配额和保留策略。

## Configuration and Limits

常用配置：SCORE_MODE、MODEL、GEMINI_BACKEND/PROJECT/LOCATION/MODEL、ALLOW_NETWORK、
RUN_GROUP、ITEMS_PER_FEED、MAX_ARTICLES、MIN_SCORE、RETRY_ATTEMPTS、OUTPUT_DIR、
STATE_PATH、PRIVATE_ARTIFACT_BUCKET/PREFIX。占位符清单见 [.env.example](../.env.example)。
DeepSeek 与 API-key 模式、独立 SMTP 见[可选接口](OPTIONAL_ADAPTERS.md)。Job 不自动发信。

来源失败时可跳过并继续其他来源；零条目不保证来源确实没有变化。抓取不是 SSRF 沙箱，
也没有浏览器隔离、统一严格响应上限或多租户授权。提示词和响应不能保证消除注入风险。
debug 日志可能包含原文或 provider 错误信息，只在受控环境使用。依赖为版本范围，
实际部署需单独完成依赖审查、权限与服务集成配置。

## Rights

[RIGHTS.md](../RIGHTS.md) 说明原创部分权利保留；既有上游 MIT 声明
[单独保留](../third_party/LICENSE-MIT-UPSTREAM.txt)。源码可见不代表新增商用授权。
