# infra/terraform

Whole-stack GCP Infrastructure-as-Code (ADR-0013). One `terraform apply` brings
up the VPC, Artifact Registry, GCS config bucket, Secret Manager secrets, CI
Workload Identity Federation, the app VM (auto-deploy on boot), the HTTPS load
balancer, and the metadata-LLM GPU VM (off by default).

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
   `WORKLOAD_IDENTITY_PROVIDER`, `CI_SERVICE_ACCOUNT`, `IMAGE_REPO`,
   `CONFIG_BUCKET`, `GCP_REGION`. Then push a `v*` tag → images land in Artifact
   Registry and `config.tgz` in the bucket.
3. **Pre-stage the embedding model** (ADR-0009 §10) and set
   `embedding_model_revision` in tfvars.
4. **Apply the rest:** `terraform apply` → note `terraform output lb_ip`.
5. **DNS:** point `server_name`'s A record at `lb_ip`. The managed cert goes
   ACTIVE ~15–60 min after it resolves.
6. SSH via IAP to watch first-boot deploy:
   `gcloud compute ssh buscasam-app --tunnel-through-iap` →
   `sudo tail -f /var/log/buscasam-startup.log`.

## Day-2

- **Redeploy / rollback:** push a new tag (CI publishes it), then on the VM
  re-pull config for that ref and run `infra/scripts/deploy.sh <ref>`.
- **Rotate a secret:** update the value in `secrets.auto.tfvars`, `terraform
  apply`, reboot the VM (or re-run startup) to regenerate `.env`.
- **GPU on/off:** `terraform apply -var metadata_llm_running=true|false`.
