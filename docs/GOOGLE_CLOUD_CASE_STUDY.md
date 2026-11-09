# Scheduled Research Processing on Google Cloud

I built Strategic Signal Scanner to support the research behind Unbound Maker
Community. Our work spans AI, smart hardware, robotics and human-computer
interaction, so useful material arrives in different forms: research papers,
developer tools, product examples and reports of emerging needs.

The scanner gives that material a consistent path from collection to editorial
review. Cloud Scheduler and Cloud Run Jobs provide the batch architecture,
Gemini supports relevance scoring, and Cloud Storage preserves state and
history between executions. I use the resulting candidates to develop topics
for community editions, discussions and project mentoring.

[中文项目叙述](PROJECT_CONTEXT.zh-CN.md) | [Entry points](../README.md#entry-points) | [Full technical guide](TECHNICAL_GUIDE.md)

## From Scattered Sources to Editorial Candidates

Finding material is only the beginning. The same announcement can appear in
several feeds; a promising title may contain little usable detail; an important
source may already have been reviewed in an earlier run. For our community,
the useful question is what a development changes for someone trying to build
something, not simply whether it is new.

I organized the workflow into capture, normalization, deduplication, scoring and
structured JSON output. Deterministic code handles source metadata and known-item checks;
the model helps assess relevance and summarize the captured material. This
division keeps the source record available when I review a model's judgment.
The scored JSON gives me a smaller, structured set of candidates to inspect before
selecting topics and writing public articles.

The work recurs, but each run has a clear end. That made a Cloud Run Job a
better fit than an always-on research service. Cloud Scheduler supplies an
authenticated trigger, while Cloud Storage preserves the deduplication state
and scored history that would otherwise disappear with the container.
Gemini's Vertex SDK path uses the runtime service account's ADC, so model
access can sit within the same Google Cloud identity model as storage access.

My role covers the Python workflow, source adapters, model integration,
container orchestration and private JSON persistence. The model provider can
be changed without replacing the capture and storage pipeline. Editorial
selection stays with me: the automation organizes research inputs, while I
decide which ideas are worth explaining and how they relate to our creators.

## End-to-End Architecture

```text
Explicit source build -> Cloud Build -> Artifact Registry container
                                                |
Cloud Scheduler -- OAuth --> Cloud Run Jobs :run API
                              |
                              v
Job runtime service account -> ADC -> Google APIs
  private GCS -> restore capture state
  sources -> normalize/deduplicate -> raw JSON
  raw JSON -> Gemini Vertex SDK -> scored JSON
  JSON state/history -> private GCS
  human -> verify evidence, select, edit and approve distribution
```

The [job entry point](../tools/cloudrun_job.py) owns this ordering and propagates
configuration to its subprocesses. The [capture/score runner](../tools/capture_and_score.py)
uses the [fetcher](../fetcher.py) and [persistent deduplication state](../state.py).
Source URLs and summaries remain in scored JSON for human review and downstream processing.
This public package does not include report rendering or date-indexed pages.

The [Dockerfile](../Dockerfile) defaults to the safe offline demo. A real Job
must explicitly override its command. The [deployment reference](TECHNICAL_GUIDE.md#deployment-reference)
builds an image with Cloud Build, stores it in Artifact Registry and attaches a
runtime service account to Cloud Run Jobs. These are explicit operator actions.

## Decision 1: A Job Rather Than an Always-On Service

**Choice:** A batch container exits after producing artifacts. Cloud Scheduler
calls the authenticated Run Jobs API using an OAuth service account.
The trigger identity receives invocation rights on the target job; the runtime
identity receives data/model access. Neither needs a downloaded account key.

**Tradeoff:** A successful trigger request means execution was requested, not
that capture or scoring completed. Scheduling and completion monitoring are
separate concerns. This package does not implement completion alerts or SLOs.

The reference uses one task, parallelism one and no platform-level job retries.
Model calls still have bounded internal retries. One task is not a distributed
lock: two executions can overlap, and the operator must serialize them.

## Decision 2: Gemini Through ADC and the Vertex SDK Path

**Choice:** Use `google-genai` with `GEMINI_BACKEND=vertex`, a configured project,
location and model. Cloud Run supplies ADC through its attached runtime service
account. The primary path requires no `GEMINI_API_KEY` or model-provider secret.
The account needs appropriate model permissions, such as `roles/aiplatform.user`.

Actual client construction in [signal_replay.py](../tools/signal_replay.py):

```python
        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=http_options,
        )
```

The request uses `client.models.generate_content(model=model, contents=prompt)`.
Scoring itself defaults to `mock`; the backend defaults to `api_key`, so Vertex
must be selected explicitly. The [configuration guide](TECHNICAL_GUIDE.md#gemini-through-vertex-and-adc)
shows the required environment and exact request-loop excerpt.

**Tradeoff:** The SDK is a transport, not an evidence validator. Rate limits,
transient server errors and timeouts receive bounded exponential backoff;
nonretryable failures stop the run rather than silently substituting mock scores.
There is no global rate controller or retry jitter. Supported model/location
combinations and quotas need verification in the target project.

The output normalizer preserves source metadata from the captured input rather
than trusting the model to reproduce it. It parses JSON and bounds relevance
scores to 0–5; it is not a complete schema validator or a fact-checking service.
The [prompt](../tools/system_instruction.md) treats source text as untrusted data
and requests conservative scoring when evidence is weak.

## Decision 3: Private JSON Persistence

**Choice:** Cloud Run's temporary filesystem is working space. A private GCS
bucket restores capture state across runs. After capture/scoring,
the job uploads only raw/scored/state JSON to that configured bucket.
There is no public report destination, HTML uploader or history enumeration.

The [storage functions](../tools/cloudrun_job.py) allowlist ordinary JSON files
and skip symlinks, HTML and unrelated files. The target must match the private
bucket configuration. Obsolete report settings fail before cleanup or network
operations.

**Tradeoff:** GCS writes are not a multi-object transaction. There are no
generation preconditions or distributed locks, so overlapping writers can lose
updates. Capture state advances before scoring; a later failure needs deliberate
replay from raw JSON. Same-day results can be replaced. History retention and
private bucket policies remain operator responsibilities.

## From Research Candidates to Community Learning

The scanner and the community publishing platform address successive parts of
the same work. The scanner helps me find and review technical material; the
publishing platform delivers the selected stories and provides a stable reading experience.
I connect them through research, editing and community discussion rather than
an automatic publishing step.

I also demonstrated the workflow at a June 25 GDG Community Talk. The technical
discussion centers on a practical question: how do you turn a model call into
a repeatable process with source records, persistent state and a human decision
at the end? That question applies beyond newsletters to research digests,
developer-resource monitoring and other recurring information tasks.

The reference package makes the workflow inspectable. Developers can follow
the source-handling, deduplication, scoring and JSON output paths, then examine
where cloud execution and authentication boundaries sit.

## Working With the Code

The [capture/score entry point](../tools/capture_and_score.py) accepts explicit
source configuration and produces raw and scored JSON. The [job wrapper](../tools/cloudrun_job.py)
adds state restoration and private persistence. The [technical guide](TECHNICAL_GUIDE.md)
documents configuration and explicit cloud deployment commands.

The container starts in help-only mode. Live capture, model calls and cloud
deployment are separate operator actions. A nonproduction environment should
be used to configure IAM, model access, bucket policies and scheduling before rollout.

## Complete Workflow, Minimal Public Data

The generic source registry, parser, local state and JSON output remain so the
research workflow can be reproduced without the private editorial presentation layer. [Optional adapters](OPTIONAL_ADAPTERS.md) retain
DeepSeek, Gemini API-key mode and SMTP without making them primary dependencies.

Source visibility
does not grant reuse or commercial permission; see [RIGHTS.md](../RIGHTS.md) and
the preserved [upstream notice](../third_party/LICENSE-MIT-UPSTREAM.txt).

## Google Cloud References

- [Cloud Run Jobs execution](https://cloud.google.com/run/docs/execute/jobs)
- [Cloud Run service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Storage preconditions](https://cloud.google.com/storage/docs/request-preconditions)
