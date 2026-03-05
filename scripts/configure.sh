#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${PROJECT_ROOT}/.hemisphere.env"

cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Model catalog (Bash 3.2 compatible -- no associative arrays)
# Format: model_name|input_price|output_price|description
# ---------------------------------------------------------------------------

RH_COUNT=6
RH_1="claude-4.6-opus|5.00|25.00|Best reasoning, highest quality"
RH_2="gemini-2.5-pro|1.25|10.00|Strong reasoning, good value"
RH_3="gpt-5|1.25|10.00|Strong reasoning, good value"
RH_4="o3|2.00|8.00|Strong chain-of-thought reasoning"
RH_5="deepseek-r1|0.55|2.19|Budget reasoning model"
RH_6="claude-haiku-4.5|1.00|5.00|Fast, cost-effective Claude"

LH_COUNT=5
LH_1="gemini-2.5-flash|0.15|0.60|Fastest, cheapest -- recommended"
LH_2="gpt-4.1-mini|0.40|1.60|Fast, slightly higher quality"
LH_3="claude-haiku-4.5|1.00|5.00|Fast Claude, higher cost"
LH_4="gemini-2.5-pro|1.25|10.00|Higher quality, higher cost"
LH_5="deepseek-v3|0.27|1.10|Budget option, good quality"

_field() { echo "$1" | cut -d'|' -f"$2"; }

# ---------------------------------------------------------------------------
# Estimate daily cost for a typical workload (61 tasks/day)
# ---------------------------------------------------------------------------
estimate_daily_cost() {
    local in_price=$1
    local out_price=$2
    local role=$3

    if [ "$role" = "rh" ]; then
        echo "scale=2; (210000 * $in_price / 1000000 + 3000 * $out_price / 1000000) * 61 * 2" | bc
    else
        echo "scale=2; (250000 * $in_price / 1000000 + 25000 * $out_price / 1000000) * 61" | bc
    fi
}

_get_rh() {
    case $1 in
        1) echo "$RH_1";; 2) echo "$RH_2";; 3) echo "$RH_3";;
        4) echo "$RH_4";; 5) echo "$RH_5";; 6) echo "$RH_6";;
    esac
}

_get_lh() {
    case $1 in
        1) echo "$LH_1";; 2) echo "$LH_2";; 3) echo "$LH_3";;
        4) echo "$LH_4";; 5) echo "$LH_5";;
    esac
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

for i in $(seq 1 $RH_COUNT); do
    entry=$(_get_rh "$i")
    name=$(_field "$entry" 1)
    inp=$(_field "$entry" 2)
    outp=$(_field "$entry" 3)
    desc=$(_field "$entry" 4)
    daily=$(estimate_daily_cost "$inp" "$outp" "rh")
    printf "  %-3s %-22s  \$%5s   \$%5s   \$%8s  %s\n" "$i" "$name" "$inp" "$outp" "$daily" "$desc"
done

echo ""
read -rp "  Select Master model [1-${RH_COUNT}] (default: 1): " rh_choice
rh_choice=${rh_choice:-1}

if [ "$rh_choice" -lt 1 ] 2>/dev/null || [ "$rh_choice" -gt "$RH_COUNT" ] 2>/dev/null; then
    echo "  Invalid selection. Using default (claude-4.6-opus)."
    rh_choice=1
fi

rh_entry=$(_get_rh "$rh_choice")
RH_MODEL=$(_field "$rh_entry" 1)
RH_IN=$(_field "$rh_entry" 2)
RH_OUT=$(_field "$rh_entry" 3)
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

for i in $(seq 1 $LH_COUNT); do
    entry=$(_get_lh "$i")
    name=$(_field "$entry" 1)
    inp=$(_field "$entry" 2)
    outp=$(_field "$entry" 3)
    desc=$(_field "$entry" 4)
    daily=$(estimate_daily_cost "$inp" "$outp" "lh")
    printf "  %-3s %-22s  \$%5s   \$%5s   \$%8s  %s\n" "$i" "$name" "$inp" "$outp" "$daily" "$desc"
done

echo ""
read -rp "  Select Emissary model [1-${LH_COUNT}] (default: 1): " lh_choice
lh_choice=${lh_choice:-1}

if [ "$lh_choice" -lt 1 ] 2>/dev/null || [ "$lh_choice" -gt "$LH_COUNT" ] 2>/dev/null; then
    echo "  Invalid selection. Using default (gemini-2.5-flash)."
    lh_choice=1
fi

lh_entry=$(_get_lh "$lh_choice")
LH_MODEL=$(_field "$lh_entry" 1)
LH_IN=$(_field "$lh_entry" 2)
LH_OUT=$(_field "$lh_entry" 3)
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
