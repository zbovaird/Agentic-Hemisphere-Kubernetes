# Automated GCP Setup via Gemini Browser Extension

> **For use with the Google Gemini Chrome extension.** Open this file on GitHub in Chrome with the Gemini extension enabled, then ask Gemini: *"Follow the instructions on this page to set up my GCP project."*

---

## What This Does

This guide instructs the Gemini browser extension to walk you through setting up a Google Cloud Platform project for the Agentic-Hemisphere-Kubernetes deployment. Gemini will guide you through each step in the GCP Console, filling in the correct values and clicking the right buttons.

**Estimated time:** 10-15 minutes  
**Estimated cost:** $0 (uses free tier / free credits)  
**Budget cap:** $25 (configured in Step 4)

---

## Prerequisites

Before starting, make sure you have:
- A Google account
- Chrome browser with the [Gemini extension](https://chrome.google.com/webstore) installed
- A credit card for GCP billing (you won't be charged beyond the budget you set)

---

## Instructions for Gemini

> Gemini: Please guide the user through each of the following steps. At each step, navigate to the specified URL, wait for the page to load, then help the user complete the action described. Confirm completion before moving to the next step. If any step fails, explain the error and suggest a fix.

### Step 1: Create a New GCP Project

1. Navigate to: `https://console.cloud.google.com/projectcreate`
2. In the **Project name** field, enter: `agentic-hemisphere-test`
3. Leave **Organization** as the default (or "No organization" for personal accounts)
4. Click **Create**
5. Wait for the project to be created (a notification will appear)
6. **Important:** Note the **Project ID** shown below the project name — it may differ from the name (e.g., `agentic-hemisphere-test-123456`). The user will need this later.

### Step 2: Link a Billing Account

1. Navigate to: `https://console.cloud.google.com/billing`
2. If the user has no billing account:
   - Click **Create Account** or **Link a billing account**
   - Follow the prompts to enter payment information
   - Google provides **$300 in free credits** for new accounts
3. If the user already has a billing account:
   - Go to `https://console.cloud.google.com/billing/linkedaccount`
   - Make sure the `agentic-hemisphere-test` project is linked to an active billing account
4. Confirm billing is active by checking that the project appears under **Billing → Account Management**

### Step 3: Select the Project

1. Navigate to: `https://console.cloud.google.com/home/dashboard`
2. Click the **project selector dropdown** at the top of the page
3. Select **agentic-hemisphere-test** from the list
4. Confirm the project name appears in the top bar

### Step 4: Set a Budget Alert ($25)

1. Navigate to: `https://console.cloud.google.com/billing/budgets/create`
2. Fill in the budget form:
   - **Name:** `hemisphere-test-budget`
   - **Projects:** Select `agentic-hemisphere-test`
   - **Amount:** Select **Specified amount** and enter `25`
3. On the **Thresholds** section, set these alert thresholds:
   - `50%` — Forecast
   - `75%` — Forecast
   - `90%` — Actual
   - `100%` — Actual
4. Under **Notifications:**
   - Check **Email alerts to billing admins and users**
5. Click **Finish** or **Save**
6. Confirm the budget appears in the budgets list

### Step 5: Enable Required APIs

Navigate to each of the following URLs and click **Enable** on each page. Wait for each API to finish enabling before moving to the next one.

1. `https://console.cloud.google.com/apis/library/container.googleapis.com` — **Kubernetes Engine API**
2. `https://console.cloud.google.com/apis/library/aiplatform.googleapis.com` — **Vertex AI API**
3. `https://console.cloud.google.com/apis/library/iam.googleapis.com` — **Identity and Access Management API**
4. `https://console.cloud.google.com/apis/library/compute.googleapis.com` — **Compute Engine API**
5. `https://console.cloud.google.com/apis/library/artifactregistry.googleapis.com` — **Artifact Registry API**
6. `https://console.cloud.google.com/apis/library/monitoring.googleapis.com` — **Cloud Monitoring API**
7. `https://console.cloud.google.com/apis/library/cloudresourcemanager.googleapis.com` — **Cloud Resource Manager API**
8. `https://console.cloud.google.com/apis/library/serviceusage.googleapis.com` — **Service Usage API**

After enabling all 8 APIs, verify by navigating to:
`https://console.cloud.google.com/apis/dashboard`

The dashboard should show all 8 APIs listed as enabled.

### Step 6: Verify Project Configuration

1. Navigate to: `https://console.cloud.google.com/home/dashboard`
2. Confirm the following are visible on the dashboard:
   - **Project name:** `agentic-hemisphere-test`
   - **Project number** and **Project ID** are displayed
   - **Billing:** Shows as linked/active
3. Tell the user to copy their **Project ID** — they will need it for the next step

### Step 7: Guide the User to Local Setup

Tell the user to open their terminal and run the following commands, replacing `YOUR_PROJECT_ID` with the Project ID from Step 6:

```
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
```

Then navigate to the cloned repository and configure Terraform:

```
cd Agentic-Hemisphere-Kubernetes/terraform
cp terraform.tfvars.example terraform.tfvars
```

Tell the user to edit `terraform.tfvars` and replace `your-gcp-project-id` with their actual Project ID.

### Step 8: Confirm Ready to Deploy

Tell the user their GCP project is fully configured and they can deploy by running:

```
cd Agentic-Hemisphere-Kubernetes
make deploy
```

Remind them:
- The estimated monthly cost is **$17-23** with the cluster running continuously
- They can run `make teardown` at any time to destroy all resources and stop charges
- The $25 budget alert will notify them if spending approaches the limit
- If they have a new GCP account, the **$300 free credit** covers months of testing

---

## Summary of What Was Configured

| Setting | Value |
|---------|-------|
| Project name | `agentic-hemisphere-test` |
| Budget | $25 with alerts at 50%, 75%, 90%, 100% |
| APIs enabled | Kubernetes Engine, Vertex AI, IAM, Compute Engine, Artifact Registry, Cloud Monitoring, Cloud Resource Manager, Service Usage |
| Region | `us-central1` (configured in Terraform) |
| Cluster type | GKE Autopilot (pay-per-pod) |

---

## Troubleshooting

If Gemini encounters issues at any step:

- **"You don't have permission"** — The user may not be the project owner. Navigate to `https://console.cloud.google.com/iam-admin/iam` and check that the user's email has the **Owner** role.
- **"Billing account required"** — Go back to Step 2 and ensure billing is linked.
- **"API already enabled"** — This is fine, skip to the next API.
- **"Quota exceeded"** — For new projects, some quotas may need increasing. Navigate to `https://console.cloud.google.com/iam-admin/quotas` and request an increase for the specific resource.
