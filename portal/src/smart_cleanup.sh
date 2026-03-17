#!/bin/bash

#############################################################################
# Smart Portal Cleanup Script
#############################################################################
# Safely kills only portal-related processes without touching your browsers
#############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Smart Portal Cleanup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

#############################################################################
# Display Current State
#############################################################################
echo -e "${YELLOW}Current Memory & Swap Status:${NC}"
sysctl vm.swapusage
echo ""

#############################################################################
# Step 1: Kill Portal Python Processes (Safe)
#############################################################################
echo -e "${YELLOW}[Step 1] Killing portal Python processes...${NC}"
echo ""

# Kill daemon.py (this should close its Chrome instances gracefully)
DAEMON_PIDS=$(pgrep -f "daemon.py" 2>/dev/null || true)
if [ -n "$DAEMON_PIDS" ]; then
    echo "  Found daemon.py: $DAEMON_PIDS"
    echo "  Sending SIGTERM (graceful shutdown)..."
    echo "$DAEMON_PIDS" | xargs kill -15 2>/dev/null || true
    sleep 3  # Give it time to clean up

    # Check if still running
    STILL_RUNNING=$(pgrep -f "daemon.py" 2>/dev/null || true)
    if [ -n "$STILL_RUNNING" ]; then
        echo "  Process still running. Sending SIGKILL..."
        echo "$STILL_RUNNING" | xargs kill -9 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✓ daemon.py killed${NC}"
else
    echo "  No daemon.py processes found"
fi

# Kill entry.py
ENTRY_PIDS=$(pgrep -f "entry.py" 2>/dev/null || true)
if [ -n "$ENTRY_PIDS" ]; then
    echo "  Found entry.py: $ENTRY_PIDS"
    echo "$ENTRY_PIDS" | xargs kill -9 2>/dev/null || true
    echo -e "  ${GREEN}✓ entry.py killed${NC}"
else
    echo "  No entry.py processes found"
fi

# Kill portal_agent.py
AGENT_PIDS=$(pgrep -f "portal_agent.py" 2>/dev/null || true)
if [ -n "$AGENT_PIDS" ]; then
    echo "  Found portal_agent.py: $AGENT_PIDS"
    echo "$AGENT_PIDS" | xargs kill -9 2>/dev/null || true
    echo -e "  ${GREEN}✓ portal_agent.py killed${NC}"
else
    echo "  No portal_agent.py processes found"
fi

echo ""

#############################################################################
# Step 2: Kill ChromeDriver (Safe - these are always Selenium)
#############################################################################
echo -e "${YELLOW}[Step 2] Killing ChromeDriver processes...${NC}"
echo ""

DRIVER_COUNT=$(pgrep -i "chromedriver" 2>/dev/null | wc -l | tr -d ' ')
if [ "$DRIVER_COUNT" -gt 0 ]; then
    echo "  Found $DRIVER_COUNT ChromeDriver processes"
    pkill -9 -i "chromedriver" 2>/dev/null || true
    echo -e "  ${GREEN}✓ ChromeDriver killed${NC}"
else
    echo "  No ChromeDriver processes found"
fi

echo ""

#############################################################################
# Step 3: Kill Selenium Chrome Processes (Safe - using --test-type flag)
#############################################################################
echo -e "${YELLOW}[Step 3] Killing Selenium Chrome processes...${NC}"
echo ""

# Find Chrome processes with --test-type=webdriver flag (ONLY used by Selenium)
SELENIUM_PIDS=$(ps aux | grep -i chrome | grep "\-\-test-type=webdriver" | grep -v grep | awk '{print $2}')

if [ -n "$SELENIUM_PIDS" ]; then
    SELENIUM_COUNT=$(echo "$SELENIUM_PIDS" | wc -l | tr -d ' ')
    echo "  Found $SELENIUM_COUNT Selenium Chrome processes (--test-type=webdriver)"
    echo ""
    echo "  PIDs to kill:"
    echo "$SELENIUM_PIDS" | while read pid; do
        echo "    • $pid"
    done
    echo ""

    echo "  Killing Selenium Chrome processes..."
    echo "$SELENIUM_PIDS" | xargs kill -9 2>/dev/null || true
    sleep 1
    echo -e "  ${GREEN}✓ Selenium Chrome processes killed${NC}"
else
    echo "  No Selenium Chrome processes found"
fi

echo ""

#############################################################################
# Step 4: Verify Regular Chrome Browsers Still Running
#############################################################################
echo -e "${YELLOW}[Step 4] Verifying your regular Chrome browsers are safe...${NC}"
echo ""

NORMAL_CHROME_COUNT=$(ps aux | grep -i chrome | grep -v grep | grep -v "\-\-test-type=webdriver" | wc -l | tr -d ' ')
if [ "$NORMAL_CHROME_COUNT" -gt 0 ]; then
    echo -e "  ${GREEN}✓ Your regular Chrome browsers are still running ($NORMAL_CHROME_COUNT processes)${NC}"
else
    echo "  No regular Chrome processes found (this is normal if you closed Chrome)"
fi

echo ""

#############################################################################
# Step 5: Memory Stats
#############################################################################
echo -e "${YELLOW}[Step 5] Updated Memory Status:${NC}"
echo ""
sleep 2
sysctl vm.swapusage
echo ""

#############################################################################
# Summary
#############################################################################
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Cleanup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}What was done:${NC}"
echo "  ✓ Killed portal Python processes (daemon.py, entry.py, portal_agent.py)"
echo "  ✓ Killed ChromeDriver processes"
echo "  ✓ Killed ONLY Selenium Chrome processes (--test-type=webdriver)"
echo "  ✓ Your regular Chrome browsers are untouched"
echo ""
echo -e "${YELLOW}Next steps if memory is still high:${NC}"
echo "  1. Run: ${GREEN}sudo purge${NC} to clear inactive memory"
echo "  2. Restart your Mac to fully clear swap"
echo "  3. Check Activity Monitor for other memory hogs"
echo ""
