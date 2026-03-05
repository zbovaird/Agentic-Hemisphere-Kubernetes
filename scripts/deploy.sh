#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Agentic-Hemisphere-Kubernetes Deployment ==="
echo ""

# ---------------------------------------------------------------------------
# Step 0: Preflight checks and auto-install
# ---------------------------------------------------------------------------
echo "--- Step 0/7: Preflight checks ---"

OS="$(uname)"
HAS_BREW=false
HAS_APT=false
HAS_YUM=false
if command -v brew >/dev/null 2>&1; then HAS_BREW=true; fi
if command -v apt-get >/dev/null 2>&1; then HAS_APT=true; fi
if command -v yum >/dev/null 2>&1; then HAS_YUM=true; fi

_ensure_homebrew() {
    if $HAS_BREW; then return 0; fi
    echo ""
    echo "  Homebrew is required to install dependencies on macOS."
    read -rp "  Install Homebrew now? [Y/n]: " hb_choice
    hb_choice=${hb_choice:-y}
    if echo "$hb_choice" | grep -qi '^y'; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f /usr/local/bin/brew ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        HAS_BREW=true
    else
        echo "  ERROR: Cannot install dependencies without Homebrew."
        exit 1
    fi
}

_install_tool() {
    local tool=$1
    echo ""
    echo "  '$tool' not found. Installing..."

    case "$tool" in
        gcloud)
            if [ "$OS" = "Darwin" ]; then
                _ensure_homebrew
                brew install --cask google-cloud-sdk
                # Source completions so gcloud is available in current shell
                if [ -f "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc" ]; then
                    source "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc"
                fi
            elif $HAS_APT; then
                echo "  Installing Google Cloud SDK via apt..."
                sudo apt-get update -qq
                sudo apt-get install -y -qq apt-transport-https ca-certificates gnupg curl
                curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg 2>/dev/null
                echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
                sudo apt-get update -qq && sudo apt-get install -y -qq google-cloud-cli
            elif $HAS_YUM; then
                sudo tee /etc/yum.repos.d/google-cloud-sdk.repo >/dev/null <<'YUMEOF'
[google-cloud-cli]
name=Google Cloud CLI
baseurl=https://packages.cloud.google.com/yum/repos/cloud-sdk-el9-x86_64
enabled=1
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg
YUMEOF
                sudo yum install -y google-cloud-cli
            else
                echo "  ERROR: Cannot auto-install gcloud. Install manually:"
                echo "    https://cloud.google.com/sdk/docs/install"
                exit 1
            fi
            ;;

        terraform)
            if [ "$OS" = "Darwin" ]; then
                _ensure_homebrew
                brew tap hashicorp/tap
                brew install hashicorp/tap/terraform
            elif $HAS_APT; then
                echo "  Installing Terraform via apt..."
                sudo apt-get update -qq && sudo apt-get install -y -qq gnupg software-properties-common curl
                curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg 2>/dev/null
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
                sudo apt-get update -qq && sudo apt-get install -y -qq terraform
            elif $HAS_YUM; then
                sudo yum install -y yum-utils
                sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
                sudo yum install -y terraform
            else
                echo "  ERROR: Cannot auto-install terraform. Install manually:"
                echo "    https://developer.hashicorp.com/terraform/install"
                exit 1
            fi
            ;;

        kubectl)
            if command -v gcloud >/dev/null 2>&1; then
                echo "  Installing kubectl via gcloud..."
                gcloud components install kubectl --quiet
            elif [ "$OS" = "Darwin" ]; then
                _ensure_homebrew
                brew install kubectl
            elif $HAS_APT; then
                sudo apt-get update -qq && sudo apt-get install -y -qq kubectl
            elif $HAS_YUM; then
                sudo yum install -y kubectl
            else
                echo "  ERROR: Cannot auto-install kubectl. Install manually:"
                echo "    https://kubernetes.io/docs/tasks/tools/"
                exit 1
            fi
            ;;

        bc)
            if [ "$OS" = "Darwin" ]; then
                _ensure_homebrew
                brew install bc
            elif $HAS_APT; then
                sudo apt-get update -qq && sudo apt-get install -y -qq bc
            elif $HAS_YUM; then
                sudo yum install -y bc
            else
                echo "  ERROR: Cannot auto-install bc. Install manually:"
                echo "    brew install bc (macOS) or apt install bc (Linux)"
                exit 1
            fi
            ;;
    esac
}

MISSING=""
for cmd in gcloud terraform kubectl bc; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        MISSING="$MISSING $cmd"
    fi
done

if [ -n "$MISSING" ]; then
    echo "  Missing tools:$MISSING"
    echo ""
    read -rp "  Install them automatically? [Y/n]: " auto_install
    auto_install=${auto_install:-y}

    if echo "$auto_install" | grep -qi '^y'; then
        for cmd in $MISSING; do
            _install_tool "$cmd"
        done

        # Verify everything installed
        STILL_MISSING=""
        for cmd in gcloud terraform kubectl bc; do
            if ! command -v "$cmd" >/dev/null 2>&1; then
                STILL_MISSING="$STILL_MISSING $cmd"
            fi
        done
        if [ -n "$STILL_MISSING" ]; then
            echo ""
            echo "  ERROR: Failed to install:$STILL_MISSING"
            echo "  Please install them manually and re-run: make deploy"
            exit 1
        fi
        echo ""
        echo "  All tools installed successfully."
    else
        echo ""
        echo "  Install the missing tools manually before running this script:"
        echo "    gcloud    -> https://cloud.google.com/sdk/docs/install"
        echo "    terraform -> https://developer.hashicorp.com/terraform/install"
        echo "    kubectl   -> gcloud components install kubectl"
        echo "    bc        -> brew install bc (macOS) or apt install bc (Linux)"
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
