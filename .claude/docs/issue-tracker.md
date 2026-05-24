# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies. **`gh issue create` does NOT add the issue to the `buscasam` project board** — you must add it explicitly with `gh project item-add 11 --owner LucasACH --url <issue-url>` immediately after creation. New issues land in Status `Todo` by default. An issue that is not on the project board is invisible to triage; treat creation-without-linking as a bug.
- **Link as a sub-issue of a parent**: when an issue has a parent (e.g. a slice ticket under its PRD), make it a real GitHub sub-issue, not just a `## Parent` text reference. The CLI has no `gh sub-issue` shorthand; use the REST API:
  ```sh
  CHILD_DB_ID=$(gh api repos/LucasACH/buscasam/issues/<child-number> --jq '.id')
  gh api -X POST repos/LucasACH/buscasam/issues/<parent-number>/sub_issues -F sub_issue_id=$CHILD_DB_ID
  ```
  Note `-F` (numeric) not `-f` (string) — the API rejects a string-typed `sub_issue_id`. Verify with `gh api repos/LucasACH/buscasam/issues/<parent>/sub_issues --jq '[.[] | {number, title}]'`. The `## Parent` body section in the issue template is human-readable redundancy, not a substitute.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Linking PRs to issues

Every implementation PR must include `Closes #<issue-number>` in its body. GitHub then:

- Links the PR to the issue (visible from both)
- Auto-closes the issue when the PR merges to the default branch — no manual `gh issue close` needed
- The "Item closed" project automation flips Status to `Done` when the PR merges

## Issue lifecycle for agents

The `buscasam` project board (id `PVT_kwHOBFwsic4BYp-V`, project number `11`, URL https://github.com/users/LucasACH/projects/11) has Status column `Backlog → Ready → In progress → In review → Done`. Agents drive these transitions explicitly except for the final `Done`, which is automated on merge.

| Trigger                              | Agent action                                                              |
| ------------------------------------ | ------------------------------------------------------------------------- |
| Picking up an issue                  | Remove `needs-triage` if present; move Status to `In progress`            |
| Opening the PR (with `Closes #<n>`)  | Move Status to `In review` — signals the ticket is awaiting review        |
| Reviewer approves and merges PR      | Nothing manual. Issue auto-closes; Status auto-moves to `Done` on close   |

Never manually close the issue; the merged PR does it.

### Moving Status with `gh`

The Status field needs three IDs (project, field, option). For this repo:

```sh
PROJECT_ID=PVT_kwHOBFwsic4BYp-V
STATUS_FIELD=PVTSSF_lAHOBFwsic4BYp-VzhTuOAI
# Status option ids
BACKLOG=f75ad846
READY=61e4505c
IN_PROGRESS=47fc9ee4
IN_REVIEW=df73e18b
DONE=98236657
```

Find the project item id for an issue and update the field:

```sh
ISSUE=2
ITEM_ID=$(gh project item-list 11 --owner LucasACH --format json --limit 100 \
  | jq -r ".items[] | select(.content.number==$ISSUE) | .id")

gh project item-edit \
  --project-id "$PROJECT_ID" \
  --id "$ITEM_ID" \
  --field-id "$STATUS_FIELD" \
  --single-select-option-id "$IN_REVIEW"
```

If the option ids ever drift, re-discover them with:

```sh
gh api graphql -f query='query{user(login:"LucasACH"){projectV2(number:11){id fields(first:20){nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}}}}'
```
