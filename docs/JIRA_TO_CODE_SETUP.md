# Jira-to-Code promotion: setup and end-to-end test (SCRUM-5)

## Branch model

| Branch | Bundle target | Who writes to it |
| --- | --- | --- |
| `dev` | `dev` | Developers (PRs from `feat/<KEY>`) |
| `uat` | `uat` | Agent PRs from `agent/<KEY>-uat` |
| `main` | `prod` | Agent PRs from `agent/<KEY>-prod` |

## Repository layout

* `databricks.yml` - Declarative Automation Bundle with `dev` / `uat` / `prod` targets
* `src/` - sample ETL job (`sample_etl.py`) and pure business logic (`transformations.py`)
* `tests/` - pytest unit tests (run in CI and in the agent's pre-flight)
* `agent/promote.py` - the Jira-to-Code promotion agent
* `.github-templates/workflows/jira-promotion.yml` - runs the agent on a Jira webhook or manually
* `.github-templates/workflows/ci.yml` - pytest + `databricks bundle validate` on PRs to dev/uat/main
* `.github-templates/workflows/cd.yml` - `databricks bundle deploy` on merge to dev/uat/main

## 0. Activate the workflows (one-time)

The workflows are stored in `.github-templates/workflows/` because the tool that created this repo has no GitHub "workflows" permission. Move them into `.github/workflows/` on **each** of `main`, `dev` and `uat`, with identical content on every branch so later diffs don't touch them:

```bash
for b in main dev uat; do
  git checkout "$b" && git pull
  mkdir -p .github/workflows
  git mv .github-templates/workflows/*.yml .github/workflows/
  git commit -m "Activate CI/CD and promotion workflows" && git push
done
```

The promotion workflow must exist on `main` (the default branch): GitHub runs `repository_dispatch` and `workflow_dispatch` workflows from the default branch.

## 1. GitHub secrets (Settings > Secrets and variables > Actions)

| Secret | Purpose |
| --- | --- |
| `DATABRICKS_HOST_DEV`, `DATABRICKS_TOKEN_DEV` | Dev workspace URL + token (or service principal) |
| `DATABRICKS_HOST_UAT`, `DATABRICKS_TOKEN_UAT` | UAT workspace |
| `DATABRICKS_HOST_PROD`, `DATABRICKS_TOKEN_PROD` | Prod workspace |
| `AGENT_GITHUB_TOKEN` | Fine-grained PAT (contents, pull requests, issues: read/write). Needed so agent PRs trigger CI; falls back to `GITHUB_TOKEN` |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Optional: lets the agent comment back on the ticket |

For a single-workspace test, point all three hosts at the same workspace; the targets deploy to separate paths and tables.
Update the `catalog` / `schema` per target in `databricks.yml` to ones the deploying identity can write to.

## 2. Jira setup

1. Add statuses `Ready for UAT` and `Ready for Prod` to the project workflow.
2. Create a Jira Automation rule: trigger **Issue transitioned** to `Ready for UAT` or `Ready for Prod`, action **Send web request**:
   * URL: `https://api.github.com/repos/SGA-RushikeshGhate/jira-to-code-poc/dispatches`
   * Method: POST; headers `Accept: application/vnd.github+json`, `Authorization: Bearer <GITHUB_PAT>`
   * Body (custom data):
     `{"event_type": "jira-status-change", "client_payload": {"issue_key": "{{issue.key}}", "status": "{{issue.status.name}}"}}`

Convention: every PR title (or branch name) must contain the Jira key, e.g. `SCRUM-5: ...` or `feat/SCRUM-5`.

## 3. End-to-end test with SCRUM-5

**Stage 1 - Dev (human)**
1. Review PR `feat/SCRUM-5 -> dev` (adds `classify_order_size` + tests). CI runs pytest + `bundle validate -t dev`.
2. Merge it. CD deploys `-t dev`. Optionally run job `[dev] jira-to-code sample ETL`.
3. Move SCRUM-5 to **Ready for UAT**.

**Stage 2 - UAT (agent)**
4. The webhook (or Actions > Jira-to-Code promotion agent > Run workflow, `SCRUM-5`, `Ready for UAT`) runs the agent.
5. Expected: branch `agent/SCRUM-5-uat` created from `uat`, the dev merge diff applied, pytest + `bundle validate -t uat` pass, and PR `SCRUM-5: promote to uat` opened and assigned to the original developer.
6. Approve and merge. CD deploys `-t uat`.

**Stage 3 - Prod (agent)**
7. Move SCRUM-5 to **Ready for Prod** (or run the workflow manually with `Ready for Prod`).
8. Expected: branch `agent/SCRUM-5-prod` from `main`, the uat diff applied, validation against `-t prod`, PR `SCRUM-5: promote to prod`.
9. Merge. CD runs `databricks bundle deploy -t prod`.

**Negative tests**
* Re-run the agent after merge: it reports "nothing to promote" (idempotent).
* Commit a conflicting change to `uat` first: the agent fails with a patch-conflict message (and comments on Jira).
* Break a test on `feat/...`: CI blocks the dev PR, and the agent pre-flight would block promotion.

Tip: use `dry_run: true` on the manual workflow to exercise diff + validation without pushing.
