# GCP Setup: Assistant-Guided Walkthrough

This guide is designed for use with Gemini. If you are following this, you can ask: *"I'm on Step 2, what should I do?"* or *"Help me fill out the form in Step 4."*

---

## Step 1: Create the Project

**Action:** Go to [Project Creation](https://console.cloud.google.com/projectcreate).

- **Project Name:** `agentic-hemisphere-test`
- Leave Organization as default / "No organization"

**What to tell Gemini:** *"I've clicked Create. The Project ID it gave me is [Insert ID here]."*

---

## Step 2: Billing & Project Selection

**Action:** Ensure the project is active in the [Dashboard](https://console.cloud.google.com/home/dashboard).

**Action:** Confirm billing is linked in [Billing Account Management](https://console.cloud.google.com/billing).

- If you don't have a billing account, create one — new accounts get **$300 in free credits**
- Link `agentic-hemisphere-test` to your billing account

**What to tell Gemini:** *"I'm in the Billing console, does everything look linked?"*

---

## Step 3: Set the $25 Budget

**Action:** Go to [Create Budget](https://console.cloud.google.com/billing/budgets/create).

| Field | Value |
|-------|-------|
| Budget Name | `hemisphere-test-budget` |
| Projects | `agentic-hemisphere-test` |
| Budget Type | Specified amount |
| Target Amount | `25` |

**Thresholds:**

| Percent | Type |
|---------|------|
| 50% | Forecasted |
| 75% | Forecasted |
| 90% | Actual |
| 100% | Actual |

Enable **Email alerts to billing admins and users** under notifications.

**What to tell Gemini:** *"I'm setting the thresholds, which ones were they again?"*

---

## Step 4: Enable Required APIs

**Option A — One command in your terminal (fastest):**

If you already have `gcloud` installed and authenticated, run this single command to enable all 8 APIs at once:

```bash
gcloud services enable container.googleapis.com aiplatform.googleapis.com iam.googleapis.com compute.googleapis.com artifactregistry.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com serviceusage.googleapis.com --project=agentic-hemisphere-test
```

**Option B — Click through the console:**

Open these links one by one and click **Enable**:

1. [Kubernetes Engine](https://console.cloud.google.com/apis/library/container.googleapis.com)
2. [Vertex AI](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)
3. [IAM](https://console.cloud.google.com/apis/library/iam.googleapis.com)
4. [Compute Engine](https://console.cloud.google.com/apis/library/compute.googleapis.com)
5. [Artifact Registry](https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com)
6. [Cloud Monitoring](https://console.cloud.google.com/apis/library/monitoring.googleapis.com)
7. [Cloud Resource Manager](https://console.cloud.google.com/apis/library/cloudresourcemanager.googleapis.com)
8. [Service Usage](https://console.cloud.google.com/apis/library/serviceusage.googleapis.com)

**What to tell Gemini:** *"I've enabled the APIs. Can you double-check the list for me?"*

---

## Step 5: Final Confirmation

**Action:** Check the [API Dashboard](https://console.cloud.google.com/apis/dashboard) and confirm all 8 APIs are enabled.

**What to tell Gemini:** *"Everything looks good on the dashboard. What do I do in the terminal next?"*

---

## Step 6: Local Terminal Setup

Open a terminal and run these commands, replacing `YOUR_PROJECT_ID` with the Project ID from Step 1:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
```

Then configure Terraform:

```bash
cd Agentic-Hemisphere-Kubernetes/terraform
cp terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and set `project_id` to your actual Project ID.

**What to tell Gemini:** *"I've set my project ID in terraform.tfvars. Am I ready to deploy?"*

---

## Step 7: Deploy

From the repository root:

```bash
cd Agentic-Hemisphere-Kubernetes
make deploy
```

This provisions the GKE Autopilot cluster, IAM bindings, Vertex AI endpoint, monitoring dashboard, and deploys all Kubernetes resources.

To tear everything down and stop all charges:

```bash
make teardown
```

---

## Quick Reference

| Item | Value |
|------|-------|
| Project Name | `agentic-hemisphere-test` |
| Budget | `25` USD |
| Region | `us-central1` |
| Cluster Type | GKE Autopilot |
| APIs to Enable | 8 (listed in Step 4) |
| Deploy Command | `make deploy` |
| Teardown Command | `make teardown` |
| Estimated Monthly Cost | ~$18-28 during active testing |

---

## Why This Format Works

- **Direct Links:** Each step links to the exact GCP Console page, so Gemini can tell you exactly where to click without searching menus.
- **Specific Values:** Project names, budget amounts, and commands are in `code blocks` so Gemini can read them back clearly.
- **Checkpoints:** The "What to tell Gemini" prompts keep the assistant in the loop to validate your progress at each stage.
