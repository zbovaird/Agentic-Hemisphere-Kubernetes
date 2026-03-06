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
    echo "  Opening your browser to sign in to Google Cloud..."
    echo ""
    if ! gcloud auth login --launch-browser 2>/dev/null; then
        echo ""
        echo "  Browser did not open automatically."
        echo "  Run this command manually and follow the URL it prints:"
        echo ""
        echo "    gcloud auth login --no-launch-browser"
        echo ""
        echo "  Then re-run: make deploy"
        exit 1
    fi

    echo ""
    echo "  Setting up application-default credentials..."
    echo "  Your browser will open once more."
    echo ""
    if ! gcloud auth application-default login --launch-browser 2>/dev/null; then
        echo ""
        echo "  Browser did not open automatically."
        echo "  Run this command manually:"
        echo ""
        echo "    gcloud auth application-default login --no-launch-browser"
        echo ""
        echo "  Then re-run: make deploy"
        exit 1
    fi

    if ! gcloud auth print-access-token >/dev/null 2>&1; then
        echo ""
        echo "  ERROR: Authentication failed. Please run these manually:"
        echo "    gcloud auth login"
        echo "    gcloud auth application-default login"
        echo ""
        echo "  Then re-run: make deploy"
        exit 1
    fi
    echo ""
    echo "  Authenticated successfully."
else
    AUTHED_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
    if [ -n "$AUTHED_ACCOUNT" ]; then
        echo "  Authenticated as: $AUTHED_ACCOUNT"
    fi
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

# 1. Check terraform.tfvars
if [ -z "$GCP_PROJECT" ] || [ "$GCP_PROJECT" = "your-gcp-project-id" ]; then
    if [ -f terraform/terraform.tfvars ]; then
        GCP_PROJECT=$(grep 'project_id' terraform/terraform.tfvars | cut -d'"' -f2)
    fi
fi

# 2. Check gcloud config
if [ -z "$GCP_PROJECT" ] || [ "$GCP_PROJECT" = "your-gcp-project-id" ]; then
    GCP_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
fi

# 3. If found, confirm with user (they may have multiple projects)
if [ -n "$GCP_PROJECT" ] && [ "$GCP_PROJECT" != "your-gcp-project-id" ]; then
    echo ""
    echo "  Detected GCP Project: $GCP_PROJECT"
    read -rp "  Use this project? [Y/n] or type a different Project ID: " project_input
    project_input=${project_input:-y}

    if echo "$project_input" | grep -qi '^y$'; then
        : # keep current GCP_PROJECT
    elif echo "$project_input" | grep -qi '^n$'; then
        read -rp "  Enter your GCP Project ID: " GCP_PROJECT
    else
        GCP_PROJECT="$project_input"
    fi
fi

# 4. Still no project -- guide user to create one
if [ -z "$GCP_PROJECT" ] || [ "$GCP_PROJECT" = "your-gcp-project-id" ]; then
    echo ""
    echo "  No GCP project found."
    echo ""
    echo "  If you don't have a project yet, create one in your browser:"
    echo "    https://console.cloud.google.com/projectcreate"
    echo ""
    echo "  For a full walkthrough (billing, budget, APIs), see:"
    echo "    CHROME_INSTRUCTIONS.md"
    echo ""
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
# Step 3b: Ensure Compute Engine default service account is enabled
# ---------------------------------------------------------------------------
PROJECT_NUMBER=$(gcloud projects describe "$GCP_PROJECT" --format='value(projectNumber)' 2>/dev/null || true)

if [ -n "$PROJECT_NUMBER" ]; then
    COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    SA_STATUS=$(gcloud iam service-accounts describe "$COMPUTE_SA" \
        --project="$GCP_PROJECT" --format='value(disabled)' 2>/dev/null || true)

    if [ "$SA_STATUS" = "True" ]; then
        echo "  Compute Engine default service account is disabled."
        echo "  Re-enabling: $COMPUTE_SA"
        echo ""
        if ! gcloud iam service-accounts enable "$COMPUTE_SA" --project="$GCP_PROJECT" 2>/dev/null; then
            echo ""
            echo "  ERROR: Could not re-enable the Compute Engine service account."
            echo "  Please enable it manually in the GCP Console:"
            echo "    https://console.cloud.google.com/iam-admin/serviceaccounts?project=${GCP_PROJECT}"
            echo ""
            echo "  Or run:"
            echo "    gcloud iam service-accounts enable ${COMPUTE_SA} --project=${GCP_PROJECT}"
            echo ""
            echo "  Then re-run: make deploy"
            exit 1
        fi
        echo "  Service account re-enabled."
        echo ""
    fi
fi

# ---------------------------------------------------------------------------
# Step 4: Terraform
# ---------------------------------------------------------------------------
echo "--- Step 4/7: Provisioning infrastructure ---"

cd terraform
terraform init

_needs_import() {
    local addr="$1"
    if terraform state list 2>/dev/null | grep -q "^${addr}$"; then
        return 1
    fi
    return 0
}

_try_import_gke() {
    if [ -f terraform.tfvars ]; then
        CLUSTER_NAME=$(grep '^cluster_name' terraform.tfvars 2>/dev/null | sed 's/.*= *"//;s/".*//' || true)
    fi
    CLUSTER_NAME="${CLUSTER_NAME:-hemisphere-cluster}"
    if gcloud container clusters describe "$CLUSTER_NAME" \
        --region="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
        echo "  Importing existing GKE cluster into Terraform state..."
        terraform import \
            'module.gke.google_container_cluster.autopilot' \
            "projects/${GCP_PROJECT}/locations/${GCP_REGION}/clusters/${CLUSTER_NAME}" \
            2>/dev/null || true
    fi
}

_try_import_registry() {
    if gcloud artifacts repositories describe hemisphere-repo \
        --location="$GCP_REGION" --project="$GCP_PROJECT" >/dev/null 2>&1; then
        echo "  Importing existing Artifact Registry into Terraform state..."
        terraform import \
            'module.registry.google_artifact_registry_repository.hemisphere' \
            "projects/${GCP_PROJECT}/locations/${GCP_REGION}/repositories/hemisphere-repo" \
            2>/dev/null || true
    fi
}

_try_import_vertex() {
    ENDPOINT_ID=$(gcloud ai endpoints list \
        --region="$GCP_REGION" --project="$GCP_PROJECT" \
        --filter="displayName='hemisphere-endpoint'" \
        --format='value(name)' 2>/dev/null | head -1 || true)
    if [ -n "$ENDPOINT_ID" ]; then
        echo "  Importing existing Vertex AI Endpoint into Terraform state..."
        terraform import \
            'module.vertex.google_vertex_ai_endpoint.hemisphere' \
            "$ENDPOINT_ID" \
            2>/dev/null || true
    fi
}

_try_import_iam() {
    local sa_ids="rh-planner-sa lh-executor-sa hemisphere-operator-sa"
    local tf_names="rh_planner lh_executor operator"
    set -- $tf_names
    for sa_id in $sa_ids; do
        tf_name="$1"; shift
        addr="module.iam.google_service_account.${tf_name}"
        if _needs_import "$addr"; then
            if gcloud iam service-accounts describe "${sa_id}@${GCP_PROJECT}.iam.gserviceaccount.com" \
                --project="$GCP_PROJECT" >/dev/null 2>&1; then
                echo "  Importing existing service account ${sa_id} into Terraform state..."
                terraform import "$addr" \
                    "projects/${GCP_PROJECT}/serviceAccounts/${sa_id}@${GCP_PROJECT}.iam.gserviceaccount.com" \
                    2>/dev/null || true
            fi
        fi
    done
}

echo "  Checking for pre-existing GCP resources to import..."
if _needs_import 'module.gke.google_container_cluster.autopilot'; then
    _try_import_gke
fi
if _needs_import 'module.registry.google_artifact_registry_repository.hemisphere'; then
    _try_import_registry
fi
if _needs_import 'module.vertex.google_vertex_ai_endpoint.hemisphere'; then
    _try_import_vertex
fi
_try_import_iam

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
