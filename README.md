# Agentic-Hemisphere-Kubernetes

Bicameral AI agent architecture deployed on Kubernetes. This project implements the **Master-Emissary** (Right Hemisphere / Left Hemisphere) orchestration model as a cloud-native system using GKE Autopilot, a custom Kubernetes operator, and Vertex AI.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GKE Autopilot Cluster                     │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  owner namespace  │    │     employee namespace        │   │
│  │                   │    │                               │   │
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
│  │ manager namespace │  (Reserved for future TBAC/gateway)   │
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
| **RH Planner** | Architectural reasoning, plan generation, diff review | `rh-planner` | `owner` |
| **LH Executor** | Task execution, tool calls via MCP, ephemeral | `lh-executor` | `employee` |
| **Operator** | Watches `AgentTask` CRDs, spawns/manages LH pods | `operator` | `owner` |

### Signal Protocol

Communication between hemispheres follows the **2% Signaling Protocol** -- only high-signal metadata is exchanged via `AgentTask` Custom Resources:

- **APPROVE** -- RH confirms LH output is aligned
- **SUPPRESS** -- RH detects drift, forces rollback
- **ESCALATE** -- LH hits clarification threshold (5 iterations)
- **SURPRISE** -- LH prediction deviates from actual outcome

## Cost Benchmark

The bicameral architecture saves ~50% on LLM costs compared to a monolithic Opus-only approach by routing implementation work through Gemini 2.5 Flash (100x cheaper tokens) while reserving Opus for planning and review.

A restaurant POS scenario benchmark is included:

```bash
python scripts/pos_benchmark.py --days 30 --output-dir benchmark-results/
```

| Metric | Bicameral | Monolithic | Savings |
|--------|-----------|------------|---------|
| Daily cost (61 tasks) | $74.90 | $155.21 | 51.7% |
| Monthly (30 days) | $2,247 | $4,656 | $2,409 |
| Cost per employee txn | $0.68 | $1.19 | 43.3% |

See [docs/pos-benchmark-analysis.md](docs/pos-benchmark-analysis.md) for the full breakdown including per-task token counts, infrastructure costs, and methodology.

A built-in cost tracking module (`docker/rh-planner/app/cost/tracker.py`) records token usage, latency, and GKE pod-seconds per task in production, with structured logging for aggregation.

## GCP Setup

For first-time setup, see [CHROME_INSTRUCTIONS.md](CHROME_INSTRUCTIONS.md) for a step-by-step GCP project configuration guide (works with the Gemini Chrome extension), or [docs/gcp-setup-walkthrough.md](docs/gcp-setup-walkthrough.md) for the full manual walkthrough.

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- [Terraform](https://developer.hashicorp.com/terraform/install) (>= 1.5)
- [Docker](https://docs.docker.com/get-docker/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) (or install via `gcloud components install kubectl`)
- Python >= 3.11

## Quickstart

```bash
# 1. Clone the repo
git clone https://github.com/zbovaird/Agentic-Hemisphere-Kubernetes.git
cd Agentic-Hemisphere-Kubernetes

# 2. Set up Python environment
make setup
source .venv/bin/activate

# 3. Run tests (no cluster needed)
make test

# 4. Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# 5. Configure Terraform
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars with your project_id

# 6. Deploy everything
make deploy
```

## Docker Images

Container images for all three components (RH Planner, LH Executor, Operator) are built and pushed automatically as part of `make deploy`. The deployment script (`scripts/deploy.sh`) handles:

1. Terraform provisioning (GKE cluster, IAM, Vertex AI, monitoring)
2. kubectl credential configuration
3. Docker build and push to Google Container Registry
4. Kubernetes manifest application (CRDs, RBAC, deployments)

You do not need to build or push images manually. If you want to build images separately:

```bash
make build   # Build all three images locally
make push    # Push to GCR (requires gcloud auth configure-docker)
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
- **Pod security** enforces `restricted` Pod Security Standard: no privilege escalation, read-only root filesystem, non-root user, all capabilities dropped.
- **Network policies** implement default-deny with explicit allow rules per namespace.
- **gVisor** sandboxes all LH executor pods at the kernel level.

## Project Structure

```
├── terraform/          # Infrastructure-as-Code (GKE, IAM, Vertex AI, monitoring)
├── docker/
│   ├── rh-planner/     # Right Hemisphere: planning & review agent
│   │   └── app/cost/   # Cost tracking module for bicameral vs monolithic comparison
│   └── lh-executor/    # Left Hemisphere: ephemeral task executor
├── operator/           # Kopf-based Kubernetes operator (Corpus Callosum)
├── k8s/                # Kustomize manifests (base + dev/prod overlays)
├── tests/              # Unit, integration, and benchmark tests (202 tests)
├── scripts/            # Setup, deployment, and benchmark automation
├── docs/               # GCP setup walkthrough, POS benchmark analysis
└── .github/workflows/  # CI pipeline
```

## License

MIT License -- Copyright (c) 2026 Zach Bovaird. See [LICENSE](LICENSE) for details.
