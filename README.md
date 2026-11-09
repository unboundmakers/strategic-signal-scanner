# Strategic Signal Scanner

A Google Cloud research pipeline for Unbound Maker Community, built with
Cloud Run Jobs, Gemini and Cloud Storage.

I built the scanner to organize research, developer tools and product examples
for community articles, discussions and project mentoring. It collects source
material, removes known entries and produces scored JSON for human review.

[Google Cloud case study](docs/GOOGLE_CLOUD_CASE_STUDY.md) |
[中文说明](README.zh-CN.md) | [Technical guide](docs/TECHNICAL_GUIDE.md) |
[Optional adapters](docs/OPTIONAL_ADAPTERS.md) | [Rights](RIGHTS.md)

## Architecture

```text
Cloud Build -> Artifact Registry -> Cloud Run Jobs
Cloud Scheduler -- OAuth --> Run Jobs :run API
Job service account -> ADC/IAM -> Gemini + private Cloud Storage

restore capture state -> capture -> normalize/deduplicate -> raw JSON
-> Gemini Vertex SDK -> scored JSON and selected candidates
-> persist raw/scored/state JSON to the private bucket
-> human review and downstream editorial work
```

The public implementation covers capture, deduplication, model integration,
structured output and private persistence. Source URLs, dates, summaries and
scores remain JSON fields. Content presentation and distribution sit downstream.

## Entry Points

Python 3.11+ is required. Inspect command options without network access:

```sh
python3 -B tools/capture_and_score.py --help
python3 -B tools/score_raw_rss.py --help
```

For live use, install the requirements, configure the model project/location,
and supply an operator-owned source/input. The [technical guide](docs/TECHNICAL_GUIDE.md)
provides explicit capture and deployment commands. Live capture and model calls
are opt-in operations that may incur charges. Default scoring is local mock;
`--mode gemini` or `--score-mode gemini` explicitly selects a real provider.

## Modules

| Module | Purpose |
| --- | --- |
| `fetcher.py`, `sources.py`, `tools/rss_capture.py` | Capture adapters and a generic official-source registry |
| `state.py` | Canonical URL/title/content keys and source refresh state |
| `tools/signal_replay.py`, `tools/score_raw_rss.py` | Provider transport, retries, metadata preservation and scored JSON |
| `tools/capture_and_score.py`, `tools/cloudrun_job.py` | Batch orchestration and private GCS persistence |
| `mailer.py` | Standalone optional SMTP utility, not called by the batch job |

## Cloud Configuration

The main model path uses `google-genai` with `GEMINI_BACKEND=vertex`, a configured
project, location and model, and the runtime service account's ADC. Vertex needs
no provider API key. Cloud persistence is enabled explicitly through
`PRIVATE_ARTIFACT_BUCKET`. Only raw/scored JSON and `state.json` are uploaded.

The container default prints help and exits. The deployed Job must explicitly
select `tools/cloudrun_job.py`. The working output directory must be dedicated:
the job removes previous raw/scored files there, but retains capture state.
GCS history is not automatically deleted. Overlapping runs have no distributed
lock or generation preconditions, so operators must serialize writes.

## Rights

Original/new contributions reserve all rights; commercial use requires prior
written permission. Existing MIT permissions on upstream portions remain in
effect. See [RIGHTS.md](RIGHTS.md) and the [upstream notice](LICENSE-MIT-UPSTREAM.txt).
