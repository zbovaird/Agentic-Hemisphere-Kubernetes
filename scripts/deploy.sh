#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Agentic-Hemisphere-Kubernetes Deployment ==="
echo ""

# ---------------------------------------------------------------------------
# Step 0: Preflight checks
# ---------------------------------------------------------------------------
echo "--- Step 0/7: Preflight checks ---"

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
# Step 1: Model configuration (always interactive)
# ---------------------------------------------------------------------------
echo "--- Step 1/7: Model configuration ---"

CONFIG_FILE="${PROJECT_ROOT}/.hemisphere.env"

"${SCRIPT_DIR}/configure.sh"

# shellcheck source=/dev/null
source "$CONFIG_FILE"

RH_MODEL="${RH_MODEL:-claude-4.6-opus}"
LH_MODEL="${LH_MODEL:-gemini-2.5-flash}"

echo "Master model:   $RH_MODEL"
echo "Emissary model: $LH_MODEL"
echo ""

# ---------------------------------------------------------------------------
# Step 2: GCP project and region selection
# ---------------------------------------------------------------------------
echo "--- Step 2/7: GCP project and region ---"

GCP_PROJECT="${GCP_PROJECT:-}"

if [ -z "$GCP_PROJECT" ]; then
    if [ -f terraform/terraform.tfvars ]; then
        GCP_PROJECT=$(grep 'project_id' terraform/terraform.tfvars | cut -d'"' -f2)
    fi
fi

if [ -z "$GCP_PROJECT" ] || [ "$GCP_PROJECT" = "your-gcp-project-id" ]; then
    echo ""
    echo "  No GCP project configured."
    read -rp "  Enter your GCP Project ID: " GCP_PROJECT
    if [ -z "$GCP_PROJECT" ]; then
        echo "  ERROR: Project ID is required."
        exit 1
    fi
fi

echo ""
echo "  GCP Project: $GCP_PROJECT"
echo ""

# --- Region selection ---
echo "  Select a GCP region for deployment:"
echo ""

declare -a REGIONS
REGIONS[1]="us-east1"
REGIONS[2]="us-central1"
REGIONS[3]="us-west1"
REGIONS[4]="europe-west1"
REGIONS[5]="europe-west4"
REGIONS[6]="asia-southeast1"
REGIONS[7]="asia-northeast1"

declare -A REGION_DESC
REGION_DESC[1]="South Carolina, USA"
REGION_DESC[2]="Iowa, USA"
REGION_DESC[3]="Oregon, USA"
REGION_DESC[4]="Belgium, EU"
REGION_DESC[5]="Netherlands, EU"
REGION_DESC[6]="Singapore, Asia"
REGION_DESC[7]="Tokyo, Japan"

for i in $(seq 1 ${#REGIONS[@]}); do
    printf "    %s) %-20s  %s\n" "$i" "${REGIONS[$i]}" "${REGION_DESC[$i]}"
done

echo ""
read -rp "  Select region [1-${#REGIONS[@]}] (default: 1): " region_choice
region_choice=${region_choice:-1}

if [ -z "${REGIONS[$region_choice]+x}" ]; then
    echo "  Invalid selection. Using default (us-east1)."
    region_choice=1
fi

GCP_REGION="${REGIONS[$region_choice]}"
echo ""
echo "  Selected: $GCP_REGION (${REGION_DESC[$region_choice]})"
echo ""

# --- Write/update terraform.tfvars ---
TFVARS_FILE="${PROJECT_ROOT}/terraform/terraform.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
    cp "${PROJECT_ROOT}/terraform/terraform.tfvars.example" "$TFVARS_FILE"
fi

# Update project_id and region in tfvars (portable sed for macOS and Linux)
if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s/^project_id.*/project_id   = \"${GCP_PROJECT}\"/" "$TFVARS_FILE"
    sed -i "s/^region.*/region       = \"${GCP_REGION}\"/" "$TFVARS_FILE"
else
    sed -i '' "s/^project_id.*/project_id   = \"${GCP_PROJECT}\"/" "$TFVARS_FILE"
    sed -i '' "s/^region.*/region       = \"${GCP_REGION}\"/" "$TFVARS_FILE"
fi

REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/hemisphere-repo"
OVERLAY="${DEPLOY_OVERLAY:-dev}"

echo "  Project:  $GCP_PROJECT"
echo "  Region:   $GCP_REGION"
echo "  Registry: $REGISTRY"
echo "  Overlay:  $OVERLAY"
echo ""

# ---------------------------------------------------------------------------
# Step 2b: GitHub linking (optional)
# ---------------------------------------------------------------------------
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
# Step 3: Enable required GCP APIs
# ---------------------------------------------------------------------------
echo "--- Step 3/7: Enabling GCP APIs ---"

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
# Step 4: Terraform
# ---------------------------------------------------------------------------
echo "--- Step 4/7: Provisioning infrastructure ---"

cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
cd "$PROJECT_ROOT"

echo ""

# ---------------------------------------------------------------------------
# Step 5: Configure kubectl
# ---------------------------------------------------------------------------
echo "--- Step 5/7: Configuring kubectl ---"

CLUSTER_NAME=$(cd terraform && terraform output -raw cluster_name)
REGISTRY=$(cd terraform && terraform output -raw registry_url)
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT"

echo "Registry: $REGISTRY"
echo ""

# ---------------------------------------------------------------------------
# Step 6: Build and push container images via Cloud Build
# ---------------------------------------------------------------------------
echo "--- Step 6/7: Building container images (Cloud Build) ---"

gcloud services enable cloudbuild.googleapis.com --project="$GCP_PROJECT" --quiet

gcloud builds submit . \
    --project="$GCP_PROJECT" \
    --config=cloudbuild.yaml \
    --substitutions="_REGISTRY=${REGISTRY}" \
    --quiet

echo "Images built and pushed to ${REGISTRY} via Cloud Build."
echo ""

# ---------------------------------------------------------------------------
# Step 7: Apply Kubernetes manifests
# ---------------------------------------------------------------------------
echo "--- Step 7/7: Applying Kubernetes manifests ---"

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
