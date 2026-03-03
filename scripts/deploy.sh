#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Agentic-Hemisphere-Kubernetes Deployment ==="
echo ""

# ---------------------------------------------------------------------------
# Resolve GCP project and region
# ---------------------------------------------------------------------------
GCP_PROJECT="${GCP_PROJECT:-}"
GCP_REGION="${GCP_REGION:-us-central1}"

if [ -z "$GCP_PROJECT" ]; then
    if [ -f terraform/terraform.tfvars ]; then
        GCP_PROJECT=$(grep 'project_id' terraform/terraform.tfvars | cut -d'"' -f2)
    else
        echo "ERROR: GCP_PROJECT not set and terraform/terraform.tfvars not found."
        echo "Either export GCP_PROJECT or:"
        echo "  cp terraform/terraform.tfvars.example terraform/terraform.tfvars"
        echo "  # then edit terraform.tfvars with your project_id"
        exit 1
    fi
fi

REGISTRY="gcr.io/${GCP_PROJECT}"
OVERLAY="${DEPLOY_OVERLAY:-dev}"

echo "Project:  $GCP_PROJECT"
echo "Region:   $GCP_REGION"
echo "Registry: $REGISTRY"
echo "Overlay:  $OVERLAY"
echo ""

# ---------------------------------------------------------------------------
# Step 0: Preflight checks
# ---------------------------------------------------------------------------
echo "--- Step 0/6: Preflight checks ---"

MISSING=""
for cmd in gcloud terraform docker kubectl bc; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING="$MISSING $cmd"
    fi
done

if [ -n "$MISSING" ]; then
    echo "ERROR: Required tools not found:$MISSING"
    echo ""
    echo "Install the missing tools before running this script:"
    echo "  gcloud    -> https://cloud.google.com/sdk/docs/install"
    echo "  terraform -> https://developer.hashicorp.com/terraform/install"
    echo "  docker    -> https://docs.docker.com/get-docker/"
    echo "  kubectl   -> gcloud components install kubectl"
    echo "  bc        -> brew install bc (macOS) or apt install bc (Linux)"
    exit 1
fi

if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running. Start Docker Desktop and try again."
    exit 1
fi

echo "All prerequisites found."
echo ""

# ---------------------------------------------------------------------------
# Step 1: Model configuration
# ---------------------------------------------------------------------------
echo "--- Step 1/6: Model configuration ---"

CONFIG_FILE="${PROJECT_ROOT}/.hemisphere.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "No model configuration found. Running interactive setup..."
    echo ""
    "${SCRIPT_DIR}/configure.sh"
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

RH_MODEL="${RH_MODEL:-claude-4.6-opus}"
LH_MODEL="${LH_MODEL:-gemini-2.5-flash}"

echo "Master model:   $RH_MODEL"
echo "Emissary model: $LH_MODEL"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Enable required GCP APIs
# ---------------------------------------------------------------------------
echo "--- Step 2/6: Enabling GCP APIs ---"

gcloud services enable \
    container.googleapis.com \
    aiplatform.googleapis.com \
    iam.googleapis.com \
    compute.googleapis.com \
    containerregistry.googleapis.com \
    monitoring.googleapis.com \
    cloudresourcemanager.googleapis.com \
    serviceusage.googleapis.com \
    iamcredentials.googleapis.com \
    --project="$GCP_PROJECT" --quiet

echo "APIs enabled."
echo ""

# ---------------------------------------------------------------------------
# Step 3: Terraform
# ---------------------------------------------------------------------------
echo "--- Step 3/6: Provisioning infrastructure ---"

cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
cd "$PROJECT_ROOT"

echo ""

# ---------------------------------------------------------------------------
# Step 4: Configure kubectl
# ---------------------------------------------------------------------------
echo "--- Step 4/6: Configuring kubectl ---"

CLUSTER_NAME=$(cd terraform && terraform output -raw cluster_name)
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT"

echo ""

# ---------------------------------------------------------------------------
# Step 5: Build and push container images
# ---------------------------------------------------------------------------
echo "--- Step 5/6: Building and pushing container images ---"

gcloud auth configure-docker --quiet

docker build -t "${REGISTRY}/rh-planner:latest" docker/rh-planner/
docker build -t "${REGISTRY}/lh-executor:latest" docker/lh-executor/
docker build -t "${REGISTRY}/operator:latest" operator/

docker push "${REGISTRY}/rh-planner:latest"
docker push "${REGISTRY}/lh-executor:latest"
docker push "${REGISTRY}/operator:latest"

echo "Images pushed to ${REGISTRY}."
echo ""

# ---------------------------------------------------------------------------
# Step 6: Apply Kubernetes manifests
# ---------------------------------------------------------------------------
echo "--- Step 6/6: Applying Kubernetes manifests ---"

kubectl apply -f operator/crds/
sed "s/PROJECT_ID/${GCP_PROJECT}/g" operator/config/rbac.yaml | kubectl apply -f -

TMP_K8S=$(mktemp -d)
trap 'rm -rf "$TMP_K8S"' EXIT
cp -r k8s "$TMP_K8S/"

# Substitute all placeholders in the overlay
OVERLAY_FILE="$TMP_K8S/k8s/overlays/${OVERLAY}/kustomization.yaml"
sed -i.bak "s/GCR_REGISTRY_PLACEHOLDER/${GCP_PROJECT}/g" "$OVERLAY_FILE"
rm -f "${OVERLAY_FILE}.bak"

# Substitute model placeholders in base manifests
for f in "$TMP_K8S"/k8s/base/*.yaml; do
    sed -i.bak \
        -e "s/RH_MODEL_PLACEHOLDER/${RH_MODEL}/g" \
        -e "s/LH_MODEL_PLACEHOLDER/${LH_MODEL}/g" \
        "$f"
    rm -f "${f}.bak"
done

kubectl apply -k "$TMP_K8S/k8s/overlays/${OVERLAY}"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Models:"
echo "  Master (RH):   $RH_MODEL"
echo "  Emissary (LH): $LH_MODEL"
echo ""
echo "Check status:"
echo "  kubectl get pods -n owner"
echo "  kubectl get pods -n employee"
echo "  kubectl get agenttasks --all-namespaces"
