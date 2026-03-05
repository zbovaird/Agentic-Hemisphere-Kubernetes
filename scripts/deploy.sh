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
    if ! command -v "$cmd" >/dev/null 2>&1; then
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

# --- Check for Bash 4+ (needed by configure.sh on some older versions) ---
# The scripts are now Bash 3.2 compatible, but we still verify a sane shell.
BASH_MAJOR="${BASH_VERSINFO[0]:-0}"
if [ "$BASH_MAJOR" -lt 3 ]; then
    echo ""
    echo "WARNING: Bash $BASH_VERSION detected. Bash 3.2+ is required."
    echo ""
    if [ "$(uname)" = "Darwin" ]; then
        echo "  Install a newer Bash with Homebrew:"
        echo "    brew install bash"
        echo ""
        read -rp "  Install now? [Y/n]: " install_bash
        install_bash=${install_bash:-y}
        if echo "$install_bash" | grep -qi '^y'; then
            if command -v brew >/dev/null 2>&1; then
                brew install bash
                echo ""
                echo "  Bash installed. Please re-run: make deploy"
                exit 0
            else
                echo "  ERROR: Homebrew not found. Install from https://brew.sh"
                exit 1
            fi
        else
            echo "  Cannot continue without Bash 3.2+."
            exit 1
        fi
    else
        echo "  Install a newer Bash with your package manager:"
        echo "    apt install bash  (Debian/Ubuntu)"
        echo "    yum install bash  (RHEL/CentOS)"
        exit 1
    fi
fi

# --- Check gcloud authentication ---
if ! gcloud auth print-access-token >/dev/null 2>&1; then
    echo ""
    echo "  GCP authentication required."
    echo "  Running: gcloud auth login"
    echo ""
    gcloud auth login
    gcloud auth application-default login
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

# --- Region selection (Bash 3.2 compatible) ---
echo "  Select a GCP region for deployment:"
echo ""

REGION_COUNT=7
printf "    %s) %-20s  %s\n" "1" "us-east1"          "South Carolina, USA"
printf "    %s) %-20s  %s\n" "2" "us-central1"       "Iowa, USA"
printf "    %s) %-20s  %s\n" "3" "us-west1"          "Oregon, USA"
printf "    %s) %-20s  %s\n" "4" "europe-west1"      "Belgium, EU"
printf "    %s) %-20s  %s\n" "5" "europe-west4"      "Netherlands, EU"
printf "    %s) %-20s  %s\n" "6" "asia-southeast1"   "Singapore, Asia"
printf "    %s) %-20s  %s\n" "7" "asia-northeast1"   "Tokyo, Japan"

echo ""
read -rp "  Select region [1-${REGION_COUNT}] (default: 1): " region_choice
region_choice=${region_choice:-1}

case "$region_choice" in
    1) GCP_REGION="us-east1";        region_label="South Carolina, USA";;
    2) GCP_REGION="us-central1";     region_label="Iowa, USA";;
    3) GCP_REGION="us-west1";        region_label="Oregon, USA";;
    4) GCP_REGION="europe-west1";    region_label="Belgium, EU";;
    5) GCP_REGION="europe-west4";    region_label="Netherlands, EU";;
    6) GCP_REGION="asia-southeast1"; region_label="Singapore, Asia";;
    7) GCP_REGION="asia-northeast1"; region_label="Tokyo, Japan";;
    *) echo "  Invalid selection. Using default (us-east1)."
       GCP_REGION="us-east1"; region_label="South Carolina, USA";;
esac

echo ""
echo "  Selected: $GCP_REGION ($region_label)"
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
