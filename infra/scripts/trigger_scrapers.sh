#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="${1:-dev}"
REGION="us-east-1"

if [[ ! "$ENVIRONMENT" =~ ^(dev|prod)$ ]]; then
    echo -e "${RED}❌ Error: Environment must be 'dev' or 'prod'${NC}"
    echo "Usage: $0 [dev|prod]"
    exit 1
fi

echo -e "${BLUE}🚀 Triggering all scraping Lambda functions in ${YELLOW}${ENVIRONMENT}${BLUE} environment...${NC}"
echo ""

# Array of Lambda function names (without environment suffix)
declare -a SCRAPERS=(
    "ircc_scraping"
    "irpr_irpa_scraping"
    "refugee_law_lab_scraping"
    "forms_scraping"
)

# Function to invoke a Lambda
invoke_lambda() {
    local scraper_name=$1
    local function_name="${scraper_name}-function-${ENVIRONMENT}"
    
    echo -e "${BLUE}📡 Invoking: ${YELLOW}${function_name}${NC}"
    
    # Invoke Lambda asynchronously
    local response=$(aws lambda invoke \
        --function-name "${function_name}" \
        --invocation-type Event \
        --region "${REGION}" \
        --output json \
        /dev/null 2>&1)
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Successfully triggered: ${function_name}${NC}"
    else
        echo -e "${RED}❌ Failed to trigger: ${function_name}${NC}"
        echo -e "${RED}   Error: ${response}${NC}"
        return 1
    fi
    echo ""
}

# Invoke all scrapers
SUCCESS_COUNT=0
FAIL_COUNT=0

for scraper in "${SCRAPERS[@]}"; do
    if invoke_lambda "$scraper"; then
        ((SUCCESS_COUNT++))
    else
        ((FAIL_COUNT++))
    fi
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📊 Summary:${NC}"
echo -e "${GREEN}   ✅ Successful: ${SUCCESS_COUNT}${NC}"
if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${RED}   ❌ Failed: ${FAIL_COUNT}${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo -e "${BLUE}💡 Tip: Check CloudWatch Logs to monitor execution:${NC}"
echo -e "   aws logs tail /aws/lambda/ircc_scraping-function-${ENVIRONMENT} --follow --region ${REGION}"

if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi