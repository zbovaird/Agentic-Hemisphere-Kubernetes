# GCP Project Setup Checklist

This checklist covers everything needed to configure Google Cloud Platform for the **Agentic-Hemisphere-Kubernetes** project. Each step includes the relevant GCP Console link and the exact values to use.

**Tip:** If you have the Gemini Chrome extension, you can ask it questions like *"I'm on step 3, what do I do next?"* or *"What values should I enter for the budget?"* and it can reference this page to help you.

**Estimated time:** 10-15 minutes
**Budget cap:** $25

---

## Before You Start

You will need:
- A Google account
- A credit card for GCP billing verification (new accounts get **$300 in free credits**)

---

## Checklist

### 1. Create a GCP Project

**Where:** [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)

| Field | Value |
|-------|-------|
| Project name | `agentic-hemisphere-test` |
| Organization | Leave as default / "No organization" |

After creating the project, note your **Project ID** (shown below the name). It may have a numeric suffix like `agentic-hemisphere-test-428917`. You will need this ID throughout the setup.

- [ ] Project created
- [ ] Project ID noted: `___________________________`

---

### 2. Link Billing

**Where:** [console.cloud.google.com/billing](https://console.cloud.google.com/billing)

If you don't have a billing account yet, create one and enter your payment information. New Google Cloud accounts receive **$300 in free trial credits**, which is more than enough for months of testing.

Link the `agentic-hemisphere-test` project to your billing account.

- [ ] Billing account exists and is active
- [ ] Project is linked to billing account

---

### 3. Select the Project

**Where:** [console.cloud.google.com/home/dashboard](https://console.cloud.google.com/home/dashboard)

Use the project selector dropdown at the top of the page to switch to `agentic-hemisphere-test`. Confirm the project name appears in the top navigation bar. All subsequent steps assume this project is selected.

- [ ] Project selected in top bar

---

### 4. Create a Budget Alert

**Where:** [console.cloud.google.com/billing/budgets/create](https://console.cloud.google.com/billing/budgets/create)

| Field | Value |
|-------|-------|
| Budget name | `hemisphere-test-budget` |
| Projects | `agentic-hemisphere-test` |
| Budget type | Specified amount |
| Target amount | `25` (USD) |

Set these alert thresholds:

| Percent | Type |
|---------|------|
| 50% | Forecasted |
| 75% | Forecasted |
| 90% | Actual |
| 100% | Actual |

Under notifications, enable **Email alerts to billing admins and users**.

- [ ] Budget created at $25
- [ ] Alert thresholds configured

---

### 5. Enable APIs

Enable each of the following 8 APIs. Click the link, then click the **Enable** button on the page.

| API | Link |
|-----|------|
| Kubernetes Engine | [Enable](https://console.cloud.google.com/apis/library/container.googleapis.com) |
| Vertex AI | [Enable](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com) |
| IAM | [Enable](https://console.cloud.google.com/apis/library/iam.googleapis.com) |
| Compute Engine | [Enable](https://console.cloud.google.com/apis/library/compute.googleapis.com) |
| Artifact Registry | [Enable](https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com) |
| Cloud Monitoring | [Enable](https://console.cloud.google.com/apis/library/monitoring.googleapis.com) |
| Cloud Resource Manager | [Enable](https://console.cloud.google.com/apis/library/cloudresourcemanager.googleapis.com) |
| Service Usage | [Enable](https://console.cloud.google.com/apis/library/serviceusage.googleapis.com) |

Verify all APIs are enabled at [console.cloud.google.com/apis/dashboard](https://console.cloud.google.com/apis/dashboard).

- [ ] All 8 APIs enabled

---

### 6. Verify Everything

**Where:** [console.cloud.google.com/home/dashboard](https://console.cloud.google.com/home/dashboard)

Confirm:
- Project name shows `agentic-hemisphere-test`
- Billing status shows as active/linked
- APIs dashboard shows 8 enabled APIs

- [ ] Dashboard looks correct

---

### 7. Local Terminal Setup

Open a terminal and authenticate with Google Cloud. Replace `YOUR_PROJECT_ID` with the Project ID you noted in Step 1.

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

Open `terraform.tfvars` in a text editor and set `project_id` to your actual Project ID.

- [ ] Authenticated with `gcloud`
- [ ] `terraform.tfvars` configured

---

### 8. Deploy

From the repository root:

```bash
cd Agentic-Hemisphere-Kubernetes
make deploy
```

This provisions the GKE Autopilot cluster, IAM bindings, Vertex AI endpoint, monitoring dashboard, and deploys all Kubernetes resources.

- [ ] Deployment successful

---

## Cost Summary

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| GKE Autopilot (idle) | ~$0 (pay-per-pod) |
| GKE Autopilot (testing) | ~$17-23 |
| Vertex AI (light usage) | ~$1-5 |
| Cloud Monitoring | Free tier |
| **Total (active testing)** | **~$18-28** |

To stop all charges immediately:

```bash
make teardown
```

---

## Quick Reference

| Item | Value |
|------|-------|
| Project name | `agentic-hemisphere-test` |
| Budget | $25 |
| Region | `us-central1` |
| Cluster type | GKE Autopilot |
| APIs | 8 (listed in Step 5) |
| Teardown command | `make teardown` |

---

## Common Issues

| Problem | Solution |
|---------|----------|
| "You don't have permission" | Check IAM roles at [IAM Admin](https://console.cloud.google.com/iam-admin/iam) — your account needs **Owner** role |
| "Billing account required" | Go back to Step 2 and link billing |
| "API already enabled" | No action needed, move to the next API |
| "Quota exceeded" | Request a quota increase at [Quotas](https://console.cloud.google.com/iam-admin/quotas) |
| `gcloud` not found | Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) |
| Terraform errors | Run `terraform init` first, then check that `terraform.tfvars` has the correct Project ID |
