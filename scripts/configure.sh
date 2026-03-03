#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${PROJECT_ROOT}/.hemisphere.env"

cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Model catalog with pricing (dollars per million tokens)
# ---------------------------------------------------------------------------

declare -A RH_MODELS
declare -A RH_INPUT_PRICE
declare -A RH_OUTPUT_PRICE
declare -A RH_DESCRIPTION

RH_MODELS[1]="claude-4.6-opus"
RH_INPUT_PRICE[1]="5.00"
RH_OUTPUT_PRICE[1]="25.00"
RH_DESCRIPTION[1]="Best reasoning, highest quality"

RH_MODELS[2]="gemini-2.5-pro"
RH_INPUT_PRICE[2]="1.25"
RH_OUTPUT_PRICE[2]="10.00"
RH_DESCRIPTION[2]="Strong reasoning, good value"

RH_MODELS[3]="gpt-5"
RH_INPUT_PRICE[3]="1.25"
RH_OUTPUT_PRICE[3]="10.00"
RH_DESCRIPTION[3]="Strong reasoning, good value"

RH_MODELS[4]="o3"
RH_INPUT_PRICE[4]="2.00"
RH_OUTPUT_PRICE[4]="8.00"
RH_DESCRIPTION[4]="Strong chain-of-thought reasoning"

RH_MODELS[5]="deepseek-r1"
RH_INPUT_PRICE[5]="0.55"
RH_OUTPUT_PRICE[5]="2.19"
RH_DESCRIPTION[5]="Budget reasoning model"

RH_MODELS[6]="claude-haiku-4.5"
RH_INPUT_PRICE[6]="1.00"
RH_OUTPUT_PRICE[6]="5.00"
RH_DESCRIPTION[6]="Fast, cost-effective Claude"

declare -A LH_MODELS
declare -A LH_INPUT_PRICE
declare -A LH_OUTPUT_PRICE
declare -A LH_DESCRIPTION

LH_MODELS[1]="gemini-2.5-flash"
LH_INPUT_PRICE[1]="0.15"
LH_OUTPUT_PRICE[1]="0.60"
LH_DESCRIPTION[1]="Fastest, cheapest -- recommended"

LH_MODELS[2]="gpt-4.1-mini"
LH_INPUT_PRICE[2]="0.40"
LH_OUTPUT_PRICE[2]="1.60"
LH_DESCRIPTION[2]="Fast, slightly higher quality"

LH_MODELS[3]="claude-haiku-4.5"
LH_INPUT_PRICE[3]="1.00"
LH_OUTPUT_PRICE[3]="5.00"
LH_DESCRIPTION[3]="Fast Claude, higher cost"

LH_MODELS[4]="gemini-2.5-pro"
LH_INPUT_PRICE[4]="1.25"
LH_OUTPUT_PRICE[4]="10.00"
LH_DESCRIPTION[4]="Higher quality, higher cost"

LH_MODELS[5]="deepseek-v3"
LH_INPUT_PRICE[5]="0.27"
LH_OUTPUT_PRICE[5]="1.10"
LH_DESCRIPTION[5]="Budget option, good quality"

# ---------------------------------------------------------------------------
# Estimate daily cost for a typical workload (61 tasks/day)
# ---------------------------------------------------------------------------
estimate_daily_cost() {
    local in_price=$1
    local out_price=$2
    local role=$3

    if [ "$role" = "rh" ]; then
        # RH: ~210K input, ~3K output per task, 61 tasks, 2 phases (plan+review)
        echo "scale=2; (210000 * $in_price / 1000000 + 3000 * $out_price / 1000000) * 61 * 2" | bc
    else
        # LH: ~250K input, ~25K output per task, 61 tasks
        echo "scale=2; (250000 * $in_price / 1000000 + 25000 * $out_price / 1000000) * 61" | bc
    fi
}

# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

echo ""
echo "=============================================="
echo "  Hemisphere Model Configuration"
echo "=============================================="
echo ""
echo "Choose the LLM models for each hemisphere."
echo "Pricing is per million tokens. Daily estimates"
echo "assume ~61 tasks/day (typical dev workload)."
echo ""

# --- Master (RH) model ---
echo "----------------------------------------------"
echo "  MASTER (Right Hemisphere) -- Planning & Review"
echo "----------------------------------------------"
echo ""
printf "  %-3s %-22s %8s %9s %12s  %s\n" "#" "Model" "In/1M" "Out/1M" "~Daily" "Notes"
printf "  %-3s %-22s %8s %9s %12s  %s\n" "---" "----------------------" "--------" "---------" "------------" "-----"

for i in $(seq 1 ${#RH_MODELS[@]}); do
    daily=$(estimate_daily_cost "${RH_INPUT_PRICE[$i]}" "${RH_OUTPUT_PRICE[$i]}" "rh")
    printf "  %-3s %-22s  \$%5s   \$%5s   \$%8s  %s\n" \
        "$i" "${RH_MODELS[$i]}" "${RH_INPUT_PRICE[$i]}" "${RH_OUTPUT_PRICE[$i]}" "$daily" "${RH_DESCRIPTION[$i]}"
done

echo ""
read -rp "  Select Master model [1-${#RH_MODELS[@]}] (default: 1): " rh_choice
rh_choice=${rh_choice:-1}

if [ -z "${RH_MODELS[$rh_choice]+x}" ]; then
    echo "  Invalid selection. Using default (claude-4.6-opus)."
    rh_choice=1
fi

RH_MODEL="${RH_MODELS[$rh_choice]}"
RH_IN="${RH_INPUT_PRICE[$rh_choice]}"
RH_OUT="${RH_OUTPUT_PRICE[$rh_choice]}"
echo ""
echo "  Selected: $RH_MODEL (\$${RH_IN}/\$${RH_OUT} per 1M tokens)"
echo ""

# --- Emissary (LH) model ---
echo "----------------------------------------------"
echo "  EMISSARY (Left Hemisphere) -- Implementation"
echo "----------------------------------------------"
echo ""
printf "  %-3s %-22s %8s %9s %12s  %s\n" "#" "Model" "In/1M" "Out/1M" "~Daily" "Notes"
printf "  %-3s %-22s %8s %9s %12s  %s\n" "---" "----------------------" "--------" "---------" "------------" "-----"

for i in $(seq 1 ${#LH_MODELS[@]}); do
    daily=$(estimate_daily_cost "${LH_INPUT_PRICE[$i]}" "${LH_OUTPUT_PRICE[$i]}" "lh")
    printf "  %-3s %-22s  \$%5s   \$%5s   \$%8s  %s\n" \
        "$i" "${LH_MODELS[$i]}" "${LH_INPUT_PRICE[$i]}" "${LH_OUTPUT_PRICE[$i]}" "$daily" "${LH_DESCRIPTION[$i]}"
done

echo ""
read -rp "  Select Emissary model [1-${#LH_MODELS[@]}] (default: 1): " lh_choice
lh_choice=${lh_choice:-1}

if [ -z "${LH_MODELS[$lh_choice]+x}" ]; then
    echo "  Invalid selection. Using default (gemini-2.5-flash)."
    lh_choice=1
fi

LH_MODEL="${LH_MODELS[$lh_choice]}"
LH_IN="${LH_INPUT_PRICE[$lh_choice]}"
LH_OUT="${LH_OUTPUT_PRICE[$lh_choice]}"
echo ""
echo "  Selected: $LH_MODEL (\$${LH_IN}/\$${LH_OUT} per 1M tokens)"
echo ""

# --- Cost summary ---
rh_daily=$(estimate_daily_cost "$RH_IN" "$RH_OUT" "rh")
lh_daily=$(estimate_daily_cost "$LH_IN" "$LH_OUT" "lh")
total_daily=$(echo "scale=2; $rh_daily + $lh_daily" | bc)
total_monthly=$(echo "scale=2; $total_daily * 30" | bc)

echo "=============================================="
echo "  Cost Estimate Summary"
echo "=============================================="
echo ""
echo "  Master:   $RH_MODEL"
echo "  Emissary: $LH_MODEL"
echo ""
echo "  Estimated daily cost:   \$$total_daily"
echo "  Estimated monthly cost: \$$total_monthly"
echo ""

# --- Write config ---
cat > "$CONFIG_FILE" <<EOF
# Hemisphere model configuration
# Generated by scripts/configure.sh
# Re-run 'make configure' or 'scripts/configure.sh' to change.

RH_MODEL=$RH_MODEL
RH_MODEL_INPUT_PRICE=$RH_IN
RH_MODEL_OUTPUT_PRICE=$RH_OUT
LH_MODEL=$LH_MODEL
LH_MODEL_INPUT_PRICE=$LH_IN
LH_MODEL_OUTPUT_PRICE=$LH_OUT
EOF

echo "  Configuration saved to .hemisphere.env"
echo ""
