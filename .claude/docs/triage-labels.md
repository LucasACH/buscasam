# Triage Labels

The skills speak in terms of four canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Canonical role    | Label in our tracker | Meaning                                  |
| ----------------- | -------------------- | ---------------------------------------- |
| `needs-triage`    | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`      | `needs-info`         | Waiting on reporter for more information |
| `ready`           | `ready`              | Fully specified, ready to pick up        |
| `wontfix`         | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the ready triage label"), use the corresponding label string from this table.

## Origin Labels

Every AI-generated artifact (PRDs, slices, fixes) gets `ai`. Use it to filter automated work from human-authored issues.

## Priority Labels

Every implementation issue created by `to-issues` gets exactly one priority label:

| Label      | Meaning                                      |
| ---------- | -------------------------------------------- |
| `critical` | Blocks active work                           |
| `infra`    | Scaffolding, schemas, shared foundations     |
| `tracer`   | Normal vertical implementation slice         |
| `polish`   | Low-risk cleanup/refinement                  |

Domain labels:

- `security`
- `auth`
- `search`
- `corpus`
- `moderation`

## Cross-PRD Ordering

To enforce intra-PRD ordering, apply the `blocked` label to every slice that depends on an earlier one. Queries that list pickable work should filter `blocked` issues out. When the prerequisite ships, remove `blocked` from the next slice.

Rule of thumb: when `to-issues` opens slices for a new PRD, label every slice except the first as `blocked`. As each slice merges, unblock the next.

When closing an issue (or merging a PR that closes one), scan open issues labeled `blocked` whose `## Blocked by` section references the just-closed issue. If all their listed blockers are now closed, remove `blocked` from those issues so they become pickable.
