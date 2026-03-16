#!/bin/bash
# =============================================================================
# Docker Build Benchmark Script
# Compares original vs optimized Dockerfiles for size and build time
# =============================================================================

set -e

PROJECT_DIR="/home/alonso/Projects/Mind-Industry"
RESULTS_FILE="${PROJECT_DIR}/docker_benchmark_results.txt"

# Check if running with docker access
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to Docker daemon."
    echo "Please run with: sudo bash $0"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  Docker Build Benchmark - Old vs New"
echo "=============================================="
echo ""

# Initialize results file
{
    echo "Docker Build Benchmark Results"
    echo "=============================="
    echo "Date: $(date)"
    echo ""
} > "$RESULTS_FILE"

cd "$PROJECT_DIR"

# Function to get image size
get_image_size() {
    docker images --format "{{.Size}}" "$1" 2>/dev/null || echo "N/A"
}

# Function to get image size in bytes for comparison
get_image_size_bytes() {
    docker image inspect "$1" --format='{{.Size}}' 2>/dev/null || echo "0"
}

# Function to build and time
build_with_time() {
    local dockerfile=$1
    local tag=$2
    local context=$3
    
    echo -e "${BLUE}Building $tag (this may take a few minutes)...${NC}"
    
    local start_time end_time build_time
    start_time=$(date +%s)
    
    if docker build --no-cache -f "$dockerfile" -t "$tag" "$context" 2>&1 | tail -5; then
        end_time=$(date +%s)
        build_time=$((end_time - start_time))
        echo "$build_time"
    else
        echo "FAILED"
    fi
}

# =============================================================================
# FRONTEND BENCHMARK
# =============================================================================
echo ""
echo -e "${YELLOW}=== FRONTEND BENCHMARK ===${NC}"
{
    echo ""
    echo "=== FRONTEND ==="
} >> "$RESULTS_FILE"

# Build original frontend
echo ""
echo -e "${BLUE}[1/4] Building ORIGINAL frontend...${NC}"
FRONTEND_OLD_TIME=$(build_with_time "app/frontend/Dockerfile.original" "benchmark-frontend-old" ".")
FRONTEND_OLD_SIZE=$(get_image_size "benchmark-frontend-old")
FRONTEND_OLD_BYTES=$(get_image_size_bytes "benchmark-frontend-old")
echo -e "  ${GREEN}✓ Original: ${FRONTEND_OLD_SIZE} in ${FRONTEND_OLD_TIME}s${NC}"
echo "Original: ${FRONTEND_OLD_SIZE} (build: ${FRONTEND_OLD_TIME}s)" >> "$RESULTS_FILE"

# Build optimized frontend
echo ""
echo -e "${BLUE}[2/4] Building OPTIMIZED frontend...${NC}"
FRONTEND_NEW_TIME=$(build_with_time "app/frontend/Dockerfile" "benchmark-frontend-new" ".")
FRONTEND_NEW_SIZE=$(get_image_size "benchmark-frontend-new")
FRONTEND_NEW_BYTES=$(get_image_size_bytes "benchmark-frontend-new")
echo -e "  ${GREEN}✓ Optimized: ${FRONTEND_NEW_SIZE} in ${FRONTEND_NEW_TIME}s${NC}"
echo "Optimized: ${FRONTEND_NEW_SIZE} (build: ${FRONTEND_NEW_TIME}s)" >> "$RESULTS_FILE"

# Calculate frontend improvement
if [ "$FRONTEND_OLD_BYTES" != "0" ] && [ "$FRONTEND_NEW_BYTES" != "0" ]; then
    FRONTEND_REDUCTION=$(awk "BEGIN {printf \"%.1f\", (1 - $FRONTEND_NEW_BYTES / $FRONTEND_OLD_BYTES) * 100}")
    echo -e "  ${GREEN}→ Size reduction: ${FRONTEND_REDUCTION}%${NC}"
    echo "Size reduction: ${FRONTEND_REDUCTION}%" >> "$RESULTS_FILE"
fi

# =============================================================================
# AUTH BENCHMARK  
# =============================================================================
echo ""
echo -e "${YELLOW}=== AUTH BENCHMARK ===${NC}"
{
    echo ""
    echo "=== AUTH ==="
} >> "$RESULTS_FILE"

# Build original auth
echo ""
echo -e "${BLUE}[3/4] Building ORIGINAL auth...${NC}"
AUTH_OLD_TIME=$(build_with_time "app/auth/Dockerfile.original" "benchmark-auth-old" ".")
AUTH_OLD_SIZE=$(get_image_size "benchmark-auth-old")
AUTH_OLD_BYTES=$(get_image_size_bytes "benchmark-auth-old")
echo -e "  ${GREEN}✓ Original: ${AUTH_OLD_SIZE} in ${AUTH_OLD_TIME}s${NC}"
echo "Original: ${AUTH_OLD_SIZE} (build: ${AUTH_OLD_TIME}s)" >> "$RESULTS_FILE"

# Build optimized auth
echo ""
echo -e "${BLUE}[4/4] Building OPTIMIZED auth...${NC}"
AUTH_NEW_TIME=$(build_with_time "app/auth/Dockerfile" "benchmark-auth-new" ".")
AUTH_NEW_SIZE=$(get_image_size "benchmark-auth-new")
AUTH_NEW_BYTES=$(get_image_size_bytes "benchmark-auth-new")
echo -e "  ${GREEN}✓ Optimized: ${AUTH_NEW_SIZE} in ${AUTH_NEW_TIME}s${NC}"
echo "Optimized: ${AUTH_NEW_SIZE} (build: ${AUTH_NEW_TIME}s)" >> "$RESULTS_FILE"

# Calculate auth improvement
if [ "$AUTH_OLD_BYTES" != "0" ] && [ "$AUTH_NEW_BYTES" != "0" ]; then
    AUTH_REDUCTION=$(awk "BEGIN {printf \"%.1f\", (1 - $AUTH_NEW_BYTES / $AUTH_OLD_BYTES) * 100}")
    echo -e "  ${GREEN}→ Size reduction: ${AUTH_REDUCTION}%${NC}"
    echo "Size reduction: ${AUTH_REDUCTION}%" >> "$RESULTS_FILE"
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}                  SUMMARY                   ${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
printf "%-12s %15s %15s %12s\n" "SERVICE" "ORIGINAL" "OPTIMIZED" "REDUCTION"
printf "%-12s %15s %15s %12s\n" "--------" "--------" "---------" "---------"
printf "%-12s %15s %15s %11s%%\n" "Frontend" "$FRONTEND_OLD_SIZE" "$FRONTEND_NEW_SIZE" "$FRONTEND_REDUCTION"
printf "%-12s %15s %15s %11s%%\n" "Auth" "$AUTH_OLD_SIZE" "$AUTH_NEW_SIZE" "$AUTH_REDUCTION"
echo ""

{
    echo ""
    echo "=== SUMMARY ==="
    echo "Frontend: $FRONTEND_OLD_SIZE → $FRONTEND_NEW_SIZE ($FRONTEND_REDUCTION% reduction)"
    echo "Auth: $AUTH_OLD_SIZE → $AUTH_NEW_SIZE ($AUTH_REDUCTION% reduction)"
} >> "$RESULTS_FILE"

# =============================================================================
# CLEANUP
# =============================================================================
echo -e "${BLUE}Cleaning up benchmark images...${NC}"
docker rmi benchmark-frontend-old benchmark-frontend-new benchmark-auth-old benchmark-auth-new 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ Results saved to: $RESULTS_FILE${NC}"
echo ""
echo -e "${YELLOW}NOTE: Backend benchmark skipped (takes ~15 min due to ML model downloads).${NC}"
echo "To benchmark backend manually, run:"
echo "  sudo docker build --no-cache -f app/backend/Dockerfile.original -t backend-old ."
echo "  sudo docker build --no-cache -f app/backend/Dockerfile -t backend-new ."
echo "  sudo docker images | grep backend"
