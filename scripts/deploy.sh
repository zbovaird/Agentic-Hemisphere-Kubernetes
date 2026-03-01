#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Agentic-Hemisphere-Kubernetes Deployment ==="

GCP_PROJECT="${GCP_PROJECT:-}"
GCP_REGION="${GCP_REGION:-us-central1}"
REGISTRY="gcr.io/${GCP_PROJECT}"

if [ -z "$GCP_PROJECT" ]; then
    if [ -f terraform/terraform.tfvars ]; then
        GCP_PROJECT=$(grep 'project_id' terraform/terraform.tfvars | cut -d'"' -f2)
        REGISTRY="gcr.io/${GCP_PROJECT}"
    else
        echo "ERROR: GCP_PROJECT not set and terraform/terraform.tfvars not found."
        echo "Either export GCP_PROJECT or copy terraform/terraform.tfvars.example to terraform/terraform.tfvars"
        exit 1
    fi
fi

echo "Project: $GCP_PROJECT"
echo "Region:  $GCP_REGION"
echo ""

# Step 1: Terraform
echo "--- Step 1/4: Provisioning infrastructure ---"
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
cd "$PROJECT_ROOT"

# Step 2: Configure kubectl
echo "--- Step 2/4: Configuring kubectl ---"
CLUSTER_NAME=$(cd terraform && terraform output -raw cluster_name)
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT"

# Step 3: Build and push images
echo "--- Step 3/4: Building and pushing container images ---"
gcloud auth configure-docker --quiet

docker build -t "${REGISTRY}/rh-planner:latest" docker/rh-planner/
docker build -t "${REGISTRY}/lh-executor:latest" docker/lh-executor/
docker build -t "${REGISTRY}/operator:latest" operator/

docker push "${REGISTRY}/rh-planner:latest"
docker push "${REGISTRY}/lh-executor:latest"
docker push "${REGISTRY}/operator:latest"

# Step 4: Apply Kubernetes manifests
echo "--- Step 4/4: Applying Kubernetes manifests ---"
kubectl apply -f operator/crds/
kubectl apply -k k8s/overlays/dev/

echo ""
echo "=== Deployment complete ==="
echo "Check status: kubectl get pods --all-namespaces"
