# Full GCP Infrastructure-as-Code + CI image pipeline

## Status

Accepted (amends ADR-0009)

## Context

ADR-0009 (and its GCP addendum) defined the single-VM Docker Compose topology but
left provisioning manual ("provision by hand via gcloud/console") and kept
build-on-host. The roll-out goal is that the entire GCP footprint comes up from
one `terraform apply` + tfvars, with images built in CI rather than on the VM.

## Decision

The whole GCP footprint is Terraform, rooted at `infra/terraform/` (single root;
`metadata-llm` is now a submodule). Images are built and pushed by GitHub Actions
to Artifact Registry; the app VM pulls them. Infra config travels to the VM as a
CI-published GCS tarball, not a git checkout. Secrets live in Secret Manager and
are assembled into `.env` at boot. The app VM auto-deploys on first boot.

The steady-state topology of ADR-0009 (one stateful VM, one Compose stack, local
PGDATA + blobs) is unchanged.

## Amendments to ADR-0009

1. **§8 secrets** — secrets move from a hand-placed `.env` to **Secret Manager**.
   The VM's service account reads them at boot (`app-vm/startup.sh`) and writes
   `/opt/buscasam/infra/.env` (mode 0600). Non-secret env is templated by
   Terraform. Rotation = update the secret version + reboot/redeploy.

2. **§2 / §12 build-on-host → CI build + registry pull** — `backend` and
   `frontend` images are built by `.github/workflows/release.yml` on a `v*` tag
   and pushed to **Artifact Registry**. `compose.prod.yaml` drops `build:` and
   points `image:` at `${BUSCASAM_IMAGE_REPO}/{backend,frontend}:${BUSCASAM_VERSION}`.
   `deploy.sh` does `compose pull` (not `build`), then migrate, then `up -d`.
   Rollback is still re-running `deploy.sh <prior-ref>`; the expand/contract
   migration rule is unchanged.

3. **Config channel** — the VM no longer clones the (private) repo. CI tars the
   infra config (`compose*`, `nginx/`, `postgresql.conf`, `scripts/`) to
   `gs://<project>-buscasam-config/<ref>/config.tgz`; the VM pulls its ref.

## New infrastructure

- **Dedicated VPC** `buscasam` + subnet, **Cloud NAT** (VMs have no external IP),
  firewall (LB front-end CIDRs → app:80, IAP → :22, app subnet → GPU:11434).
- **Artifact Registry** docker repo + **GCS config bucket** (versioned).
- **Workload Identity Federation** pool/provider locked to `LucasACH/buscasam`
  + a CI service account (AR writer, bucket writer). No JSON keys.
- **App VM** (`e2-standard-2` default; tfvars knob) with a 50 GB persistent data
  disk at `/var/lib/buscasam`, a dedicated service account (secretAccessor, AR
  reader, bucket viewer, logWriter), and an unmanaged instance group.
- **Global external HTTPS LB** with a reserved static IP and a Google-managed
  cert for `server_name` → `TLS_MODE=upstream`. `:80` redirects to `:443`.

## Operational notes

- **DNS**: Terraform reserves the static IP and outputs `lb_ip`. Point
  `server_name`'s A record there; the managed cert goes ACTIVE ~15–60 min after
  DNS resolves. (`buscasam.org` for MVP; swap to the UNSAM hostname later.)
- **State** is local for MVP (no GCS backend).
- **Cost**: the metadata-LLM spot L4 defaults to `running = false`
  (scale-to-zero); the backend falls back to heuristics. The app VM is the only
  always-on compute.
- **TEI** still requires the model pre-staged offline and
  `embedding_model_revision` set before it will start (ADR-0009 §10 / ADR-0002).
