# jira-to-code-poc

Proof of concept for a Jira-to-Code agent that promotes code across isolated `dev`, `uat` and `main` branches using Declarative Automation Bundles (formerly Databricks Asset Bundles).

See [docs/JIRA_TO_CODE_SETUP.md](docs/JIRA_TO_CODE_SETUP.md) for setup and the end-to-end test plan (Jira ticket SCRUM-5).

> One-time step: move the files in `.github-templates/workflows/` to `.github/workflows/` on the `main`, `dev` and `uat` branches (see the setup guide, step 0).
