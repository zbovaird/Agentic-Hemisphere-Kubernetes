# GCP Setup Walkthrough

Step-by-step guide to configure Google Cloud Platform for testing the Agentic-Hemisphere-Kubernetes project. This covers project creation, billing, budget alerts, API enablement, and authentication.

---

## 1. Create a GCP Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top of the page
3. Click **New Project**
4. Enter a name: `agentic-hemisphere-test` (or your preference)
5. Click **Create**
6. Note your **Project ID** (e.g., `agentic-hemisphere-test-123456`) -- you'll need this for Terraform

---

## 2. Enable Billing

1. Go to **Billing** in the left sidebar (or [console.cloud.google.com/billing](https://console.cloud.google.com/billing))
2. If you don't have a billing account:
   - Click **Create Account**
   - Enter your payment information
   - Google gives new accounts **$300 in free credits** for 90 days -- this is more than enough for testing
3. Link the billing account to your project:
   - Go to **Billing → Account Management**
   - Click **Link a project**
   - Select your `agentic-hemisphere-test` project

---

## 3. Set a Budget Alert (Important!)

This prevents unexpected charges. Set it low for testing.

1. Go to **Billing → Budgets & alerts** ([console.cloud.google.com/billing/budgets](https://console.cloud.google.com/billing/budgets))
2. Click **Create Budget**
3. Configure:
   - **Name:** `hemisphere-test-budget`
   - **Projects:** Select your project
   - **Budget amount:** `$25` (or your comfort level -- $25 is plenty for testing)
   - **Budget type:** Specified amount
4. Set alert thresholds:
   - **50%** ($12.50) -- Email notification
   - **75%** ($18.75) -- Email notification
   - **90%** ($22.50) -- Email notification
   - **100%** ($25.00) -- Email notification
5. Under **Manage notifications:**
   - Check **Email alerts to billing admins and users**
   - Optionally connect a Pub/Sub topic for programmatic alerts
6. Click **Finish**

> **Note:** Budget alerts are notifications only -- they do NOT automatically stop spending. To add a hard cap, see Section 8 below.

---

## 4. Enable Required APIs

Run these commands from your terminal (or enable them in the Console under **APIs & Services → Enable APIs**):

```bash
# Authenticate first
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable all required APIs
gcloud services enable \
    container.googleapis.com \
    aiplatform.googleapis.com \
    iam.googleapis.com \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    monitoring.googleapis.com \
    cloudresourcemanager.googleapis.com \
    serviceusage.googleapis.com
```

What each API does:

| API | Purpose |
|-----|---------|
| `container.googleapis.com` | GKE (Kubernetes Engine) |
| `aiplatform.googleapis.com` | Vertex AI endpoints |
| `iam.googleapis.com` | Service accounts and Workload Identity |
| `compute.googleapis.com` | Compute Engine (required by GKE) |
| `artifactregistry.googleapis.com` | Container image registry (alternative to gcr.io) |
| `monitoring.googleapis.com` | Cloud Monitoring dashboards |
| `cloudresourcemanager.googleapis.com` | Project metadata |
| `serviceusage.googleapis.com` | API management |

---

## 5. Set Up Application Default Credentials

This lets Terraform and local tools authenticate without service account keys:

```bash
# Interactive login (opens browser)
gcloud auth login

# Set application default credentials (used by Terraform and Python SDKs)
gcloud auth application-default login

# Verify your project is set
gcloud config set project YOUR_PROJECT_ID
gcloud config list
```

---

## 6. Configure Terraform Variables

```bash
cd Agentic-Hemisphere-Kubernetes/terraform

# Copy the example file
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your project ID:

```hcl
project_id   = "agentic-hemisphere-test-123456"  # Your actual project ID
region       = "us-central1"
cluster_name = "hemisphere-cluster"

# Leave Vertex AI empty for initial testing (no model deployment = no cost)
vertex_display_name  = "hemisphere-endpoint"
vertex_model_id      = ""
vertex_traffic_split = {}

# Minimal quotas for testing
employee_cpu_quota    = "2"
employee_memory_quota = "2Gi"
employee_pod_quota    = "10"
```

---

## 7. Deploy the Infrastructure

```bash
# From the project root
cd Agentic-Hemisphere-Kubernetes

# Option A: One-command deployment
make deploy

# Option B: Step-by-step
make infra-init      # terraform init
make infra-plan      # terraform plan (review what will be created)
make infra-apply     # terraform apply (creates resources)
```

### What Gets Created (and Approximate Costs)

| Resource | Monthly Cost (idle) | Notes |
|----------|-------------------|-------|
| GKE Autopilot cluster | ~$0 idle | You only pay for running pods |
| RH Planner pod (always-on) | ~$8-10 | 250m CPU, 512Mi memory |
| Operator pod (always-on) | ~$8-10 | 250m CPU, 512Mi memory |
| LH Executor pods (ephemeral) | ~$1-3 | Only when tasks run |
| Vertex AI endpoint (no model) | $0 | No cost until you deploy a model |
| Cloud Monitoring dashboard | $0 | Free tier |
| **Total estimated** | **~$17-23/month** | |

---

## 8. (Optional) Set a Hard Spending Cap

Budget alerts only notify -- they don't stop spending. To create a hard cap:

### Option A: Use Cloud Functions to auto-disable billing

1. Create a Pub/Sub topic for budget alerts (done in Step 3)
2. Deploy a Cloud Function that disables billing when triggered:

```bash
# This is a safety net -- disables billing on the project entirely
gcloud functions deploy stop-billing \
    --runtime python311 \
    --trigger-topic budget-alerts \
    --entry-point stop_billing \
    --source scripts/budget-guard/
```

### Option B: Manual monitoring

- Check the [Billing dashboard](https://console.cloud.google.com/billing) daily during testing
- Run `make teardown` when you're done testing to destroy all resources immediately

---

## 9. Verify the Deployment

After `make deploy` completes:

```bash
# Check cluster is running
gcloud container clusters list --project YOUR_PROJECT_ID

# Get credentials for kubectl
gcloud container clusters get-credentials hemisphere-cluster \
    --region us-central1 \
    --project YOUR_PROJECT_ID

# Check namespaces
kubectl get namespaces
# Should show: owner, manager, employee

# Check pods
kubectl get pods --all-namespaces
# Should show: rh-planner and hemisphere-operator in 'owner' namespace

# Check the CRD
kubectl get crd agenttasks.hemisphere.ai

# Check resource quotas
kubectl describe resourcequota -n employee
```

---

## 10. Run a Test Task

Create a sample AgentTask to verify the full lifecycle:

```bash
kubectl apply -f - <<EOF
apiVersion: hemisphere.ai/v1
kind: AgentTask
metadata:
  name: test-task-001
  namespace: owner
spec:
  intent_id: "test-001"
  task_type: "execute"
  payload:
    command: "echo 'Hello from the Left Hemisphere'"
  target_model: "gemini-2.5-flash"
EOF

# Watch the operator spawn an LH pod
kubectl get pods -n employee -w

# Check the task status
kubectl get agenttask test-task-001 -n owner -o yaml
```

---

## 11. Run the Cost Benchmark (No Cluster Needed)

You can run the cost comparison benchmark locally without any GCP resources:

```bash
# From the project root
python scripts/benchmark.py --tasks 30 --output-dir benchmark-results/
```

This simulates 30 task lifecycles and shows the cost savings of bicameral vs monolithic.

---

## 12. Tear Down When Done

**Important:** Always tear down when you're done testing to avoid ongoing charges.

```bash
# Destroy all Terraform-managed resources
make teardown

# Verify nothing is running
gcloud container clusters list --project YOUR_PROJECT_ID
# Should show: (empty)
```

If you want to keep the project but remove all resources:
```bash
cd terraform && terraform destroy -auto-approve
```

If you want to delete the entire project (nuclear option):
```bash
gcloud projects delete YOUR_PROJECT_ID
```

---

## Cost Summary for Testing

| Scenario | Estimated Cost |
|----------|---------------|
| Deploy, run 10 test tasks, tear down same day | < $2 |
| Leave cluster running for 1 week | ~$5-6 |
| Leave cluster running for 1 month | ~$17-23 |
| Deploy a Vertex AI model (per 1K predictions) | ~$0.50-2.00 |

The $300 free credit from a new GCP account covers months of testing.

---

## Troubleshooting

**"API not enabled" errors:**
```bash
gcloud services enable container.googleapis.com aiplatform.googleapis.com
```

**"Insufficient permissions" errors:**
```bash
# Make sure you're the project owner
gcloud projects get-iam-policy YOUR_PROJECT_ID --format=json | grep -A2 "your-email"
```

**"Quota exceeded" errors:**
GKE Autopilot has default quotas. For a new project, you may need to request a quota increase:
- Go to **IAM & Admin → Quotas**
- Search for "GKE" or "Compute Engine CPUs"
- Request an increase if needed (usually approved within minutes)

**Terraform state issues:**
```bash
cd terraform
terraform init -reconfigure
terraform plan
```
