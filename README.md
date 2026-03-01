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

## Project Structure

```
├── terraform/          # Infrastructure-as-Code (GKE, IAM, Vertex AI)
├── docker/
│   ├── rh-planner/     # Right Hemisphere: planning & review agent
│   └── lh-executor/    # Left Hemisphere: ephemeral task executor
├── operator/           # Kopf-based Kubernetes operator (Corpus Callosum)
├── k8s/                # Kustomize manifests (base + dev/prod overlays)
├── tests/              # Unit, integration, and benchmark tests
├── scripts/            # Setup and deployment automation
└── .github/workflows/  # CI pipeline
```

## License

MIT License -- Copyright (c) 2026 Zach Bovaird. See [LICENSE](LICENSE) for details.
