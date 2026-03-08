#!/usr/bin/env sh
# sv_gate_count.sh — Estimate gate count for a SystemVerilog module using Yosys + slang
# Usage: ./sv_gate_count.sh <path/to/module.sv> [top_module_name] [liberty_file.lib]

# ─── Colors ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# ─── Usage ───────────────────────────────────────────────────────────────────────
usage() {
    printf "${BOLD}Usage:${RESET}\n"
    printf "  $0 <module.sv> [top_module] [liberty.lib]\n\n"
    printf "${BOLD}Arguments:${RESET}\n"
    printf "  module.sv     Path to your .sv (or .v) file (required)\n"
    printf "  top_module    Top module name (optional, auto-detected if omitted)\n"
    printf "  liberty.lib   Liberty cell library for real area estimates (optional)\n\n"
    printf "${BOLD}Examples:${RESET}\n"
    printf "  $0 onehot.sv\n"
    printf "  $0 onehot.sv onehot_to_index\n"
    printf "  $0 onehot.sv onehot_to_index mycells.lib\n"
    exit 1
}

# ─── Args ────────────────────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    usage
fi

SV_FILE="$1"
TOP_MODULE="${2:-}"
LIBERTY_FILE="${3:-}"

# ─── Checks ──────────────────────────────────────────────────────────────────────
if [ ! -f "$SV_FILE" ]; then
    printf "${RED}Error:${RESET} File not found: %s\n" "$SV_FILE"
    exit 1
fi

if ! command -v yosys > /dev/null 2>&1; then
    printf "${RED}Error:${RESET} yosys not found in PATH.\n"
    printf "  Install via OSS CAD Suite: ${CYAN}https://github.com/YosysHQ/oss-cad-suite-build${RESET}\n"
    exit 1
fi

# ─── Require slang ───────────────────────────────────────────────────────────────
if ! yosys -p "plugin -i slang" > /dev/null 2>&1; then
    printf "${RED}Error:${RESET} yosys-slang plugin not found.\n"
    printf "  slang is required for full SystemVerilog support (packed arrays, etc.)\n"
    printf "  Install: ${CYAN}https://github.com/povik/yosys-slang${RESET}\n"
    printf "  Or use OSS CAD Suite which bundles it: ${CYAN}https://github.com/YosysHQ/oss-cad-suite-build${RESET}\n"
    exit 1
fi

ABS_FILE="$(realpath "$SV_FILE")"
BASENAME="$(basename "$SV_FILE" | sed 's/\.[^.]*$//')"

# ─── Auto-detect top module name from file ───────────────────────────────────────
if [ -z "$TOP_MODULE" ]; then
    if grep -qP '' /dev/null 2>/dev/null; then
        TOP_MODULE=$(grep -oP '(?<=^module\s)\w+' "$SV_FILE" 2>/dev/null | head -1 || true)
    else
        TOP_MODULE=$(grep -E '^module\s+\w+' "$SV_FILE" | head -1 | sed 's/^module[[:space:]]*\([a-zA-Z0-9_]*\).*/\1/' || true)
    fi
    if [ -z "$TOP_MODULE" ]; then
        TOP_MODULE="$BASENAME"
    fi
    printf "${CYAN}Auto-detected top module:${RESET} %s\n" "$TOP_MODULE"
fi

# ─── Temp dir for Yosys script ───────────────────────────────────────────────────
TMPDIR_WORK="$(mktemp -d)"
YOSYS_SCRIPT="$TMPDIR_WORK/synth.ys"
YOSYS_LOG="$TMPDIR_WORK/yosys.log"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

# ─── Build Yosys script ──────────────────────────────────────────────────────────
{
    echo "plugin -i slang"
    echo "read_slang $ABS_FILE"
    echo "hierarchy -check -top $TOP_MODULE"
    echo "synth -top $TOP_MODULE"

    if [ -n "$LIBERTY_FILE" ] && [ -f "$LIBERTY_FILE" ]; then
        ABS_LIB="$(realpath "$LIBERTY_FILE")"
        echo "dfflibmap -liberty $ABS_LIB"
        echo "abc -liberty $ABS_LIB"
        echo "stat -liberty $ABS_LIB"
    else
        echo "techmap"
        echo "opt"
        echo "abc -g NAND"
        echo "stat -tech cmos"
    fi
} > "$YOSYS_SCRIPT"

# ─── Run Yosys ───────────────────────────────────────────────────────────────────
printf "\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}  Yosys Gate Count Estimator${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "  File:    ${CYAN}%s${RESET}\n" "$SV_FILE"
printf "  Module:  ${CYAN}%s${RESET}\n" "$TOP_MODULE"
printf "  Parser:  ${GREEN}slang (full SV)${RESET}\n"
if [ -n "$LIBERTY_FILE" ]; then
    printf "  Liberty: ${CYAN}%s${RESET}\n" "$LIBERTY_FILE"
fi
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

yosys "$YOSYS_SCRIPT" > "$YOSYS_LOG" 2>&1
YOSYS_EXIT=$?

cat "$YOSYS_LOG"

if [ "$YOSYS_EXIT" -ne 0 ]; then
    printf "\n${RED}Yosys exited with errors (see log above).${RESET}\n"
    exit 1
fi

# ─── Parse and display results ───────────────────────────────────────────────────
printf "\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}  Synthesis Summary: %s${RESET}\n" "$TOP_MODULE"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"

STAT_BLOCK=$(grep -A 40 "=== $TOP_MODULE ===" "$YOSYS_LOG" 2>/dev/null | head -50 || true)
if [ -z "$STAT_BLOCK" ]; then
    STAT_BLOCK=$(grep -A 40 "Number of" "$YOSYS_LOG" | head -50 || true)
fi

if [ -n "$STAT_BLOCK" ]; then
    echo "$STAT_BLOCK" | while IFS= read -r line; do
        if echo "$line" | grep -qE '^\s*(Number of|Chip area|===)'; then
            printf "${GREEN}%s${RESET}\n" "$line"
        elif echo "$line" | grep -qE '^\s+\$_|^\s+[A-Z]'; then
            printf "  %s\n" "$line"
        else
            printf "%s\n" "$line"
        fi
    done
else
    printf "${YELLOW}Warning: Could not find stat block for '%s' in log.${RESET}\n" "$TOP_MODULE"
fi

# ─── NAND2-equivalent summary ────────────────────────────────────────────────────
NAND2_EQ=$(grep -i 'NAND2-equivalent' "$YOSYS_LOG" | grep -oE '[0-9]+\.[0-9]+' | tail -1 || true)

if [ -z "$NAND2_EQ" ]; then
    NAND2_EQ=$(grep 'Number of cells:' "$YOSYS_LOG" | tail -1 | grep -oE '[0-9]+$' || true)
    LABEL="raw cell count"
else
    LABEL="NAND2-equivalent gates"
fi

if [ -n "$NAND2_EQ" ]; then
    printf "\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "  ${BOLD}%s:${RESET} ${GREEN}%s${RESET}\n" "$LABEL" "$NAND2_EQ"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
fi

printf "\n${GREEN}Done.${RESET}\n"