# infra/terraform

Whole-stack GCP Infrastructure-as-Code (ADR-0013). One `terraform apply` brings
up the VPC, Artifact Registry, GCS config bucket, Secret Manager secrets, CI
Workload Identity Federation, the app VM (auto-deploy on boot), the HTTPS load
balancer, and the metadata-LLM GPU VM (off by default).

Before enabling production traffic, complete
[`docs/production-launch.md`](../../docs/production-launch.md).

## First-time setup

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars                 # set project_id, app_version, …
cp secrets.auto.tfvars.example secrets.auto.tfvars           # fill real secret values (gitignored)
terraform init
```

## Roll-out order (chicken-and-egg around the LB IP)

1. **Stand up CI plumbing + registry first:**
   ```sh
   terraform apply -target=module.registry -target=module.cicd -target=google_project_service.apis
   terraform output workload_identity_provider ci_service_account_email image_repo_path config_bucket
   ```
2. **Wire GitHub repo variables** from those outputs:
   `WORKLOAD_IDENTITY_PROVIDER`, `CI_SERVICE_ACCOUNT`, `DEPLOY_SERVICE_ACCOUNT`,
   `IMAGE_REPO`, `CONFIG_BUCKET`, `GCP_REGION`, `GCP_ZONE`, `SERVER_NAME`. Then
   push a `v*` tag → images land in Artifact Registry and `config.tgz` in the
   bucket. (`DEPLOY_SERVICE_ACCOUNT`/`GCP_ZONE`/`SERVER_NAME` are only needed once
   the app VM exists, for the deploy job.)
3. **Apply the rest:** set `embedding_model_revision` in tfvars, then
   `terraform apply` → note `terraform output lb_ip`.
4. **Watch first-boot deploy** via IAP:
   `gcloud compute ssh buscasam-app --tunnel-through-iap` →
   `sudo tail -f /var/log/buscasam-startup.log`.
5. **Pre-stage the embedding model** through IAP (ADR-0009 §10), then redeploy
   the release tag on the VM.
6. **DNS:** point `server_name`'s A record at `lb_ip`. The managed cert goes
   ACTIVE ~15–60 min after it resolves.

## Day-2

- **Deploy:** push a `v*` tag. CI validates, builds+pushes images, publishes
  config, cuts a GitHub Release, then auto-deploys the VM over IAP SSH and
  health-checks `https://$SERVER_NAME/`. No manual `deploy.sh`.
- **Rollback / redeploy:** Actions → *release* → *Run workflow* with `ref` set to
  a previously published tag. Skips build; re-runs the deploy job for that ref.
  (Manual fallback if CI is down: SSH via IAP, re-pull that ref's `config.tgz`,
  run `infra/scripts/deploy.sh <ref>`.)
- **Rotate a secret:** update the value in `secrets.auto.tfvars`, `terraform
  apply`, reboot the VM (or re-run startup) to regenerate `.env`.
- **GPU on/off:** `terraform apply -var metadata_llm_running=true|false`.
