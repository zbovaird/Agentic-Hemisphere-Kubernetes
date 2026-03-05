# Agentic-Hemisphere-Kubernetes

Bicameral AI agent architecture deployed on Kubernetes. This project implements the **Master-Emissary** (Right Hemisphere / Left Hemisphere) orchestration model as a cloud-native system using GKE Autopilot, a custom Kubernetes operator, and Vertex AI.

## Architecture

The cluster uses three Kubernetes namespaces that represent **privilege tiers**, not business roles. You can rename them in `terraform/modules/namespaces/variables.tf` to match your domain (e.g. `control-plane`, `sandbox`, `gateway`).

| Namespace (default) | Privilege Tier | What Runs Here |
|---------------------|---------------|----------------|
| `owner` | **High-trust** — full cluster access, Vertex AI, operator | RH Planner, Kopf Operator |
| `employee` | **Sandboxed** — gVisor isolation, resource quotas, restricted PSS | Ephemeral LH Executor pods |
| `manager` | **Mid-trust** — reserved for future TBAC/API gateway | *(not yet deployed)* |

```
┌─────────────────────────────────────────────────────────────┐
│                    GKE Autopilot Cluster                     │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  owner (high-     │    │     employee (sandboxed)      │   │
│  │  trust control)   │    │                               │   │
│  │  ┌─────────────┐ │    │  ┌──────────┐  ┌──────────┐  │   │
│  │  │ RH Planner  │ │    │  │ LH Pod 1 │  │ LH Pod 2 │  │   │
│  │  │ (FastAPI)   │─┼────┼─>│ (gVisor) │  │ (gVisor) │  │   │
│  │  └─────────────┘ │    │  └──────────┘  └──────────┘  │   │
│  │                   │    │        ▲              ▲       │   │
│  │  ┌─────────────┐ │    │        │              │       │   │
│  │  │  Operator   │─┼────┼────────┴──────────────┘       │   │
│  │  │  (Kopf)     │ │    │   Spawns sandboxed LH pods    │   │
│  │  └─────────────┘ │    │                               │   │
│  └──────────────────┘    └──────────────────────────────┘   │
│                                                              │
│  ┌──────────────────┐                                        │
│  │ manager (mid-     │  (Reserved for future TBAC/gateway)   │
│  │ trust gateway)    │                                       │
│  └──────────────────┘                                        │
└──────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
   ┌─────────────┐              ┌──────────────┐
   │  Vertex AI   │              │ Workload     │
   │  Endpoint    │              │ Identity     │
   │  (Traffic    │              │ Federation   │
   │   Splitting) │              │ (No keys)    │
   └─────────────┘              └──────────────┘
```

### Components

| Component | Role | Image | Namespace |
|-----------|------|-------|-----------|
| **RH Planner** | Architectural reasoning, plan generation, diff review | `rh-planner` | `owner` (high-trust) |
| **LH Executor** | Task execution, tool calls via MCP, ephemeral | `lh-executor` | `employee` (sandboxed) |
| **Operator** | Watches `AgentTask` CRDs, spawns/manages LH pods | `operator` | `owner` (high-trust) |

### Signal Protocol

Communication between hemispheres follows the **2% Signaling Protocol** -- only high-signal metadata is exchanged via `AgentTask` Custom Resources:

- **APPROVE** -- RH confirms LH output is aligned
- **SUPPRESS** -- RH detects drift, forces rollback
- **ESCALATE** -- LH hits clarification threshold (5 iterations)
- **SURPRISE** -- LH prediction deviates from actual outcome

## Cost Benchmark

The bicameral architecture saves ~51% on LLM costs compared to a monolithic Opus-only approach by routing implementation work through Gemini 2.5 Flash (33-42x cheaper tokens) while reserving the RH model for planning and review.

A cost benchmark simulates a multi-tier workload across the three privilege levels with support for multiple RH planner models and optimization strategies:

```bash
python scripts/cost_benchmark.py                          # Default: Opus RH, no optimizations
python scripts/cost_benchmark.py --rh-model gemini-2.5-pro --all-optimizations
python scripts/cost_benchmark.py --matrix                  # Full model x optimization comparison
```

**Default (Opus RH, no optimizations):**

| Metric | Bicameral | Monolithic | Savings |
|--------|-----------|------------|---------|
| Daily cost (61 tasks) | $25.46 | $51.74 | 50.8% |
| Monthly (30 days) | $764 | $1,552 | $788 |
| Cost per high-volume txn | $0.23 | $0.40 | 42.5% |

**With alternative models and optimizations (daily cost):**

| RH Model | No Opt | All Optimizations | vs Monolithic |
|----------|--------|-------------------|---------------|
| Claude 4.6 Opus | $25.46 | $5.32 | 89.7% savings |
| GPT-5 / Gemini Pro | $7.30 | $1.79 | 96.5% savings |
| DeepSeek R1 | $3.41 | $0.97 | 98.1% savings |

See [docs/cost-benchmark-analysis.md](docs/cost-benchmark-analysis.md) for the full breakdown including per-task token counts, multi-model comparison matrix, optimization strategies, and methodology.

**Example scenario:** The branch [`benchmark/restaurant-pos`](https://github.com/zbovaird/Agentic-Hemisphere-Kubernetes/tree/benchmark/restaurant-pos) contains a restaurant POS validation run with the same benchmark logic applied to that domain.

A built-in cost tracking module (`docker/rh-planner/app/cost/tracker.py`) records token usage, latency, and GKE pod-seconds per task in production, with structured logging for aggregation.

## GCP Setup

For first-time setup, see [CHROME_INSTRUCTIONS.md](CHROME_INSTRUCTIONS.md) for a step-by-step GCP project configuration guide (works with the Gemini Chrome extension), or [docs/gcp-setup-walkthrough.md](docs/gcp-setup-walkthrough.md) for the full manual walkthrough.

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- [Terraform](https://developer.hashicorp.com/terraform/install) (>= 1.5)
- [Docker](https://docs.docker.com/get-docker/) (optional -- only needed for local builds; Cloud Build is used by default)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) (or install via `gcloud components install kubectl`)
- Python >= 3.11

## Quickstart

```bash
# 1. Clone and deploy (the script handles auth, model selection, and region)
git clone https://github.com/zbovaird/Agentic-Hemisphere-Kubernetes.git
cd Agentic-Hemisphere-Kubernetes
make deploy
```

The deploy script walks you through everything interactively:
- **Preflight check** -- verifies `gcloud`, `terraform`, `kubectl`, and `bc` are installed
- **GCP authentication** -- prompts `gcloud auth login` if not already authenticated
- **Model selection** -- choose your Master (RH) and Emissary (LH) models with pricing estimates
- **Region selection** -- pick from 7 GCP regions
- **Infrastructure provisioning** -- Terraform creates the GKE cluster, IAM, and supporting services
- **Image build** -- Cloud Build compiles and pushes container images (no local Docker needed)
- **Kubernetes deployment** -- CRDs, RBAC, and workloads applied to the cluster

To run tests locally (no cluster needed):

```bash
make setup && source .venv/bin/activate
make test
```

## Container Images

Container images for all three components (RH Planner, LH Executor, Operator) are built in the cloud via **Google Cloud Build** -- no local Docker installation required. Images are built and pushed automatically as part of `make deploy`.

The deployment script (`scripts/deploy.sh`) walks you through:

1. **Model selection** -- choose your Master (RH) and Emissary (LH) models interactively
2. **GitHub linking (optional)** -- connect your GitHub repo so images auto-rebuild on push to `main`. If you skip this, images are only built when you run `make deploy` or `make cloud-build`
3. **Terraform provisioning** -- GKE cluster, IAM, Artifact Registry, Cloud Build, Vertex AI, monitoring
4. **Cloud Build** -- builds and pushes container images to Artifact Registry (no local Docker needed)
5. **Kubernetes deployment** -- CRDs, RBAC, and workloads applied to the cluster

You do not need to build or push images manually. If you want to trigger a build separately:

```bash
make cloud-build   # Build and push via Cloud Build (no local Docker needed)
make build         # Build locally (requires Docker)
make push          # Push locally-built images to Artifact Registry
```

## Pipeline Integration

This repo is designed to be pulled into CI/CD pipelines:

### Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Test')   { steps { sh 'make setup && make test' } }
        stage('Build')  { steps { sh 'make build' } }
        stage('Deploy') { steps { sh 'make deploy' } }
    }
}
```

### Harness

Use the `scripts/deploy.sh` script as a Shell Script step, or map individual `Makefile` targets to pipeline stages.

### GitHub Actions

A CI workflow is included at `.github/workflows/ci.yml` that runs linting, tests, and Terraform validation on every push.

## Testing

Tests cover four dimensions:

| Dimension | What It Measures | Command |
|-----------|-----------------|---------|
| **Deployment Ease** | Steps from clone to running cluster | `make test` |
| **Efficiency** | Pod cold-start latency, operator reconciliation time | `make test-benchmarks` |
| **Cost** | Resource sizing, Autopilot billing estimates | `make test-benchmarks` |
| **Security** | RBAC enforcement, gVisor isolation, no privilege escalation | `make test-security` |

## Security

- **No hardcoded secrets.** All credentials use Workload Identity Federation (no service account keys).
- **Terraform state** is gitignored and should be stored in a remote backend (GCS) for team use.
- **Pod security** enforces `restricted` Pod Security Standard on the sandboxed namespace: no privilege escalation, read-only root filesystem, non-root user, all capabilities dropped.
- **Network policies** implement default-deny with explicit allow rules per namespace.
- **gVisor** sandboxes all LH executor pods at the kernel level.
- **Resource quotas** on the sandboxed namespace prevent sub-agent sprawl from starving the control plane.

## Customization

This repo is **domain-agnostic**. The namespace names, role tiers, and task profiles are generic defaults you can adapt to any use case.

| What to Customize | Where | Example |
|-------------------|-------|---------|
| Namespace names | `terraform/modules/namespaces/variables.tf` | Rename `owner` → `control-plane`, `employee` → `sandbox` |
| Resource quotas | `terraform/modules/namespaces/variables.tf` | Adjust CPU/memory/pod limits for your workload |
| RH Planner model | `docker/rh-planner/app/main.py` | Swap Opus for GPT-5, Gemini Pro, or DeepSeek R1 |
| LH Executor tools | `docker/lh-executor/` | Add MCP tools for your domain (databases, APIs, etc.) |
| Benchmark tasks | `scripts/cost_benchmark.py` | Define task profiles matching your workload |
| GCP project/region | `terraform/terraform.tfvars` | Set your `project_id` and preferred region |

For a worked example of domain-specific customization, see the [`benchmark/restaurant-pos`](https://github.com/zbovaird/Agentic-Hemisphere-Kubernetes/tree/benchmark/restaurant-pos) branch.

## Project Structure

```
├── terraform/              # Infrastructure-as-Code (GKE, IAM, Vertex AI, monitoring)
│   └── modules/
│       ├── namespaces/     # Namespace definitions and resource quotas (customize here)
│       ├── iam/            # Workload Identity Federation bindings
│       └── monitoring/     # Cloud Monitoring dashboard
├── docker/
│   ├── rh-planner/         # Right Hemisphere: planning & review agent (FastAPI)
│   │   └── app/cost/       # Cost tracking module for bicameral vs monolithic comparison
│   └── lh-executor/        # Left Hemisphere: ephemeral task executor
├── operator/               # Kopf-based Kubernetes operator (Corpus Callosum)
├── k8s/                    # Kustomize manifests (base + dev/prod overlays)
├── tests/                  # Unit, integration, and benchmark tests (202 tests)
├── scripts/                # Setup, deployment, and benchmark automation
├── docs/                   # GCP setup walkthrough, cost benchmark analysis
└── .github/workflows/      # CI pipeline
```

## License

MIT License -- Copyright (c) 2026 Zach Bovaird. See [LICENSE](LICENSE) for details.
