# Production launch runbook

Production traffic stays disabled until every item below has dated evidence.

## Release record

- [ ] Release tag: `v________`
- [ ] Commit SHA: `________`
- [ ] Operator and UTC timestamp: `________`
- [ ] Terraform apply output archived: `________`

## Mandatory prelaunch evidence

- [ ] **Restore drill:** recovery point `________`; restored into `________`; database and blob downloads verified; UTC timestamp `________`; evidence link `________`.
- [ ] **VM concurrent search + OCR benchmark:** app VM type `________`; fixture/version `________`; search concurrency `________`; OCR fixture `________`; p95 search latency `________`; lexical fallback rate `________`; index duration `________`; peak memory `________`; acceptance decision and evidence link `________`.
- [ ] **TEI model staged:** model ID `________`; pinned revision `________`; `/var/lib/buscasam/tei-cache/` verified on the app VM; TEI health verified; evidence link `________`.
- [ ] **Release published:** `v*` tag produced backend/frontend images in Artifact Registry and `<ref>/config.tgz` in the GCS config bucket; evidence link `________`.
- [ ] **DNS and certificate:** `server_name` A record resolves to Terraform `lb_ip`; Google-managed certificate is `ACTIVE`; HTTPS smoke check passed; evidence link `________`.
- [ ] **Deploy verification:** deployed tag `________`; migration completed; `db`, `tei`, `api`, `worker_default`, `worker_ocr`, `frontend`, `nginx`, and `backup` running; authenticated and lexical-fallback search smoke checks passed; evidence link `________`.
- [ ] **Rollback verification:** prior release tag `________` redeployed with `infra/scripts/deploy.sh`; migration compatibility and search smoke check passed; launch release restored afterward; evidence link `________`.

## Launch sequence

1. Stand up CI plumbing, publish the intended `v*` release tag, and confirm registry images plus `<ref>/config.tgz`.
2. Set `app_version`; apply `infra/terraform/`.
3. Pre-stage the TEI model through IAP; redeploy the release tag; complete deploy verification.
4. Point DNS at `lb_ip`; wait for the managed certificate; complete HTTPS smoke checks.
5. Run the restore drill, concurrent search + OCR benchmark, and rollback drill.
6. Archive all mandatory evidence and record launch approval.
7. Enable production traffic.

The optional metadata LLM remains off by default and is not a launch gate (ADR-0012).
