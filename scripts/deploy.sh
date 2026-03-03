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

REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/hemisphere-repo"
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
for cmd in gcloud terraform kubectl bc; do
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
    echo "  kubectl   -> gcloud components install kubectl"
    echo "  bc        -> brew install bc (macOS) or apt install bc (Linux)"
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
# Step 1b: GitHub linking (optional)
# ---------------------------------------------------------------------------
TFVARS_FILE="${PROJECT_ROOT}/terraform/terraform.tfvars"
GITHUB_OWNER=""
if [ -f "$TFVARS_FILE" ]; then
    GITHUB_OWNER=$(grep -s 'github_owner' "$TFVARS_FILE" | cut -d'"' -f2 || true)
fi

if [ -z "$GITHUB_OWNER" ]; then
    echo "----------------------------------------------"
    echo "  GitHub Integration (optional)"
    echo "----------------------------------------------"
    echo ""
    echo "  Link your GitHub repo to auto-rebuild container"
    echo "  images in Cloud Build whenever you push to main."
    echo ""
    echo "  If you skip this, images are only built when you"
    echo "  run 'make deploy' or 'make cloud-build' manually."
    echo ""
    read -rp "  Link a GitHub repo? [y/N]: " gh_choice
    gh_choice=${gh_choice:-n}

    if [[ "$gh_choice" =~ ^[Yy]$ ]]; then
        read -rp "  GitHub username or org: " gh_owner
        read -rp "  Repository name (default: Agentic-Hemisphere-Kubernetes): " gh_repo
        gh_repo=${gh_repo:-Agentic-Hemisphere-Kubernetes}

        if [ -n "$gh_owner" ]; then
            echo "" >> "$TFVARS_FILE"
            echo "# GitHub integration (auto-rebuild images on push to main)" >> "$TFVARS_FILE"
            echo "github_owner = \"${gh_owner}\"" >> "$TFVARS_FILE"
            echo "github_repo  = \"${gh_repo}\"" >> "$TFVARS_FILE"

            echo ""
            echo "  Saved: github_owner = \"${gh_owner}\""
            echo "  Saved: github_repo  = \"${gh_repo}\""
            echo ""
            echo "  NOTE: You must connect your GitHub repo to Cloud Build"
            echo "  in the GCP Console (one-time setup):"
            echo ""
            echo "    https://console.cloud.google.com/cloud-build/triggers/connect"
            echo ""
            echo "  Select 'GitHub (Cloud Build GitHub App)', authorize access,"
            echo "  and choose the ${gh_repo} repository."
            echo ""
            read -rp "  Press Enter when ready to continue..."
        else
            echo "  Skipped -- no GitHub owner provided."
        fi
    else
        echo "  Skipped -- images will be built manually via Cloud Build."
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 2: Enable required GCP APIs
# ---------------------------------------------------------------------------
echo "--- Step 2/6: Enabling GCP APIs ---"

gcloud services enable \
    container.googleapis.com \
    aiplatform.googleapis.com \
    iam.googleapis.com \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
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
REGISTRY=$(cd terraform && terraform output -raw registry_url)
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT"

echo "Registry: $REGISTRY"
echo ""

# ---------------------------------------------------------------------------
# Step 5: Build and push container images via Cloud Build
# ---------------------------------------------------------------------------
echo "--- Step 5/6: Building container images (Cloud Build) ---"

gcloud services enable cloudbuild.googleapis.com --project="$GCP_PROJECT" --quiet

gcloud builds submit . \
    --project="$GCP_PROJECT" \
    --config=cloudbuild.yaml \
    --substitutions="_REGISTRY=${REGISTRY}" \
    --quiet

echo "Images built and pushed to ${REGISTRY} via Cloud Build."
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
ESCAPED_REGISTRY=$(echo "$REGISTRY" | sed 's/[\/&]/\\&/g')
sed -i.bak "s/REGISTRY_PLACEHOLDER/${ESCAPED_REGISTRY}/g" "$OVERLAY_FILE"
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
