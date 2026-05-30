# metadata-llm

Terraform for the on-prem metadata-LLM VM that generates document TL;DRs and
keywords during indexing (see `backend/src/buscasam/core/extract.py`).

A Spot **NVIDIA L4** VM runs [Ollama](https://ollama.com) serving
`qwen2.5:7b-instruct`. Everything stays inside the GCP project — no external API.

## Why this shape

- **Spot L4** (~$0.20–0.30/hr) instead of on-demand (~$0.70/hr).
- **Scale-to-zero**: indexing is an async background job and an Ollama outage is
  non-fatal — `suggest_metadata` falls back to heuristic abstract/keywords. So
  the VM can be `STOP`ped whenever the index queue is idle without failing any
  document.
- **No external IP**: only `app_source_ranges` reach Ollama on `:11434`.

## Usage

```sh
terraform init
terraform apply -var project_id=YOUR_PROJECT -var 'app_source_ranges=["10.0.0.0/8"]'
```

Then point the backend at the output:

```sh
BUSCASAM_METADATA_LLM_ENABLED=1
BUSCASAM_METADATA_LLM_URL=<terraform output metadata_llm_url>
BUSCASAM_METADATA_LLM_MODEL=qwen2.5:7b-instruct
```

## Scale-to-zero

Stop the VM when the queue drains, start it on backlog:

```sh
terraform apply -var running=false   # STOP
terraform apply -var running=true    # RUNNING
```

For automation, drive `running` from a queue-depth check (Cloud Scheduler →
Cloud Function inspecting pending `procrastinate_jobs`). Not included here yet.
