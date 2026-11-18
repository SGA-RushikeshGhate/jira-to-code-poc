#!/usr/bin/env python3
"""Jira-to-Code promotion agent.

Ports the code change for a Jira issue to the next environment branch:
  Ready for UAT  -> diff of merged PR(s) into `dev` applied on top of `uat`
  Ready for Prod -> diff of merged PR(s) into `uat` applied on top of `main`

Steps: find merged PRs for the issue -> branch agent/<KEY>-<env> from the target
-> git apply each merge diff -> pytest + `databricks bundle validate -t <target>`
-> push -> open PR, assign/request review from the original developer -> comment on Jira.

Env vars: GITHUB_REPOSITORY, GH_TOKEN, (optional) JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN,
plus DATABRICKS_HOST / DATABRICKS_TOKEN for the bundle validation.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

import requests

GITHUB_API = "https://api.github.com"
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

STAGES = {
    "uat": {"source_branch": "dev", "target_branch": "uat", "bundle_target": "uat"},
    "prod": {"source_branch": "uat", "target_branch": "main", "bundle_target": "prod"},
}
STATUS_TO_ENV = {"ready for uat": "uat", "ready for prod": "prod"}


# ---------------------------------------------------------------- pure helpers
def resolve_target_env(status):
    return STATUS_TO_ENV.get((status or "").strip().lower())


def validate_issue_key(key):
    key = (key or "").strip().upper()
    if not ISSUE_KEY_RE.match(key):
        raise ValueError(f"Invalid Jira issue key: {key!r}")
    return key


def mentions_issue(issue_key, *texts):
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(issue_key)}(?!\d)")
    return any(pattern.search((t or "").upper()) for t in texts)


def agent_branch_name(issue_key, env):
    return f"agent/{issue_key}-{env}"


def run(cmd, check=True, capture=False):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


# ---------------------------------------------------------------- clients
class GitHub:
    def __init__(self, repo, token):
        self.repo = repo
        self.owner = repo.split("/")[0]
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _req(self, method, path, **kw):
        r = self.s.request(method, f"{GITHUB_API}{path}", timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub {method} {path} -> {r.status_code}: {r.text}")
        return r.json() if r.text else {}

    def merged_prs_for_issue(self, issue_key, base, max_pages=5):
        found = []
        for page in range(1, max_pages + 1):
            prs = self._req("GET", f"/repos/{self.repo}/pulls", params={
                "state": "closed", "base": base, "sort": "updated",
                "direction": "desc", "per_page": 100, "page": page,
            })
            if not prs:
                break
            found += [p for p in prs if p.get("merged_at")
                      and mentions_issue(issue_key, p["title"], p["head"]["ref"])]
        return sorted(found, key=lambda p: p["merged_at"])

    def find_open_pr(self, head, base):
        prs = self._req("GET", f"/repos/{self.repo}/pulls", params={
            "state": "open", "head": f"{self.owner}:{head}", "base": base})
        return prs[0] if prs else None

    def create_pr(self, head, base, title, body):
        return self._req("POST", f"/repos/{self.repo}/pulls",
                         json={"head": head, "base": base, "title": title, "body": body})

    def assign_reviewer(self, number, login):
        for path, payload in [
            (f"/repos/{self.repo}/issues/{number}/assignees", {"assignees": [login]}),
            (f"/repos/{self.repo}/pulls/{number}/requested_reviewers", {"reviewers": [login]}),
        ]:
            try:
                self._req("POST", path, json=payload)
            except RuntimeError as e:  # e.g. cannot request review from the PR author
                print(f"WARN: {e}")


class Jira:
    def __init__(self, base_url, email, token):
        self.base_url = (base_url or "").rstrip("/")
        self.auth = (email, token)
        self.enabled = bool(base_url and email and token)

    def comment(self, issue_key, text):
        print(f"[jira {issue_key}] {text}")
        if not self.enabled:
            return
        r = requests.post(f"{self.base_url}/rest/api/2/issue/{issue_key}/comment",
                          auth=self.auth, json={"body": text}, timeout=30)
        if r.status_code >= 400:
            print(f"WARN: Jira comment failed {r.status_code}: {r.text}")


# ---------------------------------------------------------------- agent
class PromotionError(Exception):
    pass


def apply_merge_diffs(prs):
    """Apply the diff of each merged PR (first-parent diff of its merge commit)."""
    applied = []
    for pr in prs:
        sha = pr["merge_commit_sha"]
        diff = run(["git", "diff", "--binary", f"{sha}^1", sha], capture=True).stdout
        if not diff.strip():
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
            f.write(diff)
            patch = f.name
        if run(["git", "apply", "--reverse", "--check", patch], check=False).returncode == 0:
            print(f"PR #{pr['number']} already present on target, skipping")
            continue
        res = run(["git", "apply", "--3way", patch], check=False, capture=True)
        if res.returncode != 0:
            raise PromotionError(
                f"Patch from PR #{pr['number']} does not apply cleanly:\n{res.stderr}{res.stdout}")
        applied.append(pr)
    return applied


def promote(issue_key, env, gh, jira, dry_run=False):
    stage = STAGES[env]
    src, tgt, bundle_target = stage["source_branch"], stage["target_branch"], stage["bundle_target"]
    branch = agent_branch_name(issue_key, env)

    prs = gh.merged_prs_for_issue(issue_key, src)
    if not prs:
        raise PromotionError(f"No merged PR into '{src}' found for {issue_key}")
    dev_prs = prs if src == "dev" else gh.merged_prs_for_issue(issue_key, "dev")
    developer = (dev_prs or prs)[0]["user"]["login"]
    print(f"Source PRs: {[p['number'] for p in prs]}, original developer: {developer}")

    run(["git", "fetch", "origin", src, tgt])
    run(["git", "checkout", "-B", branch, f"origin/{tgt}"])

    applied = apply_merge_diffs(prs)
    if not applied:
        jira.comment(issue_key, f"Jira-to-Code agent: nothing to promote, '{tgt}' already contains the change.")
        return None

    refs = ", ".join(f"#{p['number']}" for p in applied)
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"{issue_key}: promote to {env}\n\nApplied from {src} PR(s): {refs}"])

    # Pre-flight checks in the sandbox (CI runner)
    if run([sys.executable, "-m", "pytest", "-q"], check=False).returncode != 0:
        raise PromotionError("Unit tests failed on the promoted code")
    if run(["databricks", "bundle", "validate", "-t", bundle_target], check=False).returncode != 0:
        raise PromotionError(f"`databricks bundle validate -t {bundle_target}` failed")

    if dry_run:
        print("Dry run: validation passed, not pushing or opening a PR")
        return None

    run(["git", "push", "--force", "origin", f"HEAD:refs/heads/{branch}"])
    pr = gh.find_open_pr(branch, tgt)
    if pr is None:
        body = (
            f"Automated promotion of **{issue_key}** from `{src}` to `{tgt}` by the Jira-to-Code agent.\n\n"
            f"* Source PR(s): {refs}\n* Original developer: @{developer}\n"
            f"* Pre-flight: pytest passed, `databricks bundle validate -t {bundle_target}` passed\n"
        )
        pr = gh.create_pr(branch, tgt, f"{issue_key}: promote to {env}", body)
    gh.assign_reviewer(pr["number"], developer)
    jira.comment(issue_key, f"Jira-to-Code agent opened promotion PR to {tgt}: {pr['html_url']}")
    return pr


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--issue-key", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--env", choices=sorted(STAGES))
    g.add_argument("--status", help="Jira status, e.g. 'Ready for UAT'")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    issue_key = validate_issue_key(a.issue_key)
    env = a.env or resolve_target_env(a.status)
    if not env:
        print(f"Status {a.status!r} does not trigger a promotion")
        return 0

    gh = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
    jira = Jira(os.getenv("JIRA_BASE_URL"), os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    try:
        promote(issue_key, env, gh, jira, dry_run=a.dry_run)
    except PromotionError as e:
        jira.comment(issue_key, f"Jira-to-Code agent could not promote to {env}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
