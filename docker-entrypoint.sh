#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}WhatsApp Chat Auto Export - Docker${NC}"
echo -e "${GREEN}========================================${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    if [ -n "$APPIUM_PID" ]; then
        echo "Stopping Appium server (PID: $APPIUM_PID)..."
        kill $APPIUM_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Done!${NC}"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Start Appium server in background
echo -e "${YELLOW}Starting Appium server...${NC}"
appium --log-level error > /tmp/appium.log 2>&1 &
APPIUM_PID=$!

# Wait for Appium to start
echo "Waiting for Appium server to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:4723/status > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Appium server started (PID: $APPIUM_PID)${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}ERROR: Appium server failed to start${NC}"
        cat /tmp/appium.log
        exit 1
    fi
    sleep 1
done

# Ensure clean ADB state
adb kill-server 2>/dev/null || true
sleep 1

# Check ADB connection (skip for wireless ADB - let app handle it)
if [[ ! "$*" =~ "--wireless-adb" ]]; then
    echo -e "\n${YELLOW}Checking ADB connection...${NC}"
    adb devices

    DEVICE_COUNT=$(adb devices | grep -c "device$" || true)
    if [ "$DEVICE_COUNT" -eq 0 ]; then
        echo -e "${RED}ERROR: No Android device connected!${NC}"
        echo -e "${YELLOW}Please ensure your device is connected via USB${NC}"
        echo ""
        echo "For USB connection:"
        echo "  1. Enable USB debugging on your Android device"
        echo "  2. Connect via USB cable"
        echo "  3. Run: docker run --privileged -v /dev/bus/usb:/dev/bus/usb -v ./output:/output whatsapp-export --output /output"
        echo ""
        echo "For wireless ADB connection:"
        echo "  1. Enable wireless debugging on your device"
        echo "  2. Use: docker run --network=host -v ./output:/output whatsapp-export --output /output --wireless-adb <device-ip>:5555"
        echo "  3. The container will establish the connection automatically"
        exit 1
    fi

    echo -e "${GREEN}✓ Device connected${NC}"
else
    echo -e "\n${YELLOW}Wireless ADB mode - device connection will be established by application${NC}"
    echo -e "${YELLOW}Make sure your device has wireless debugging enabled and is on the same network${NC}"
fi

# Parse command
COMMAND="$1"

# If no command or help flag, show help
if [ -z "$COMMAND" ] || [ "$COMMAND" = "--help" ] || [ "$COMMAND" = "-h" ]; then
    echo -e "\n${YELLOW}Usage:${NC}"
    echo "  docker run [docker-options] whatsapp-export [export-options]"
    echo ""
    echo "Export Options:"
    echo "  --output PATH              Output directory for processed files"
    echo "  --limit N                  Limit number of chats to export"
    echo "  --no-output-media          Don't copy media to final output (transcriptions still work)"
    echo "  --no-transcribe            Skip transcription phase"
    echo "  --force-transcribe         Re-transcribe even if transcriptions exist"
    echo "  --delete-from-drive        Delete from Drive after processing"
    echo "  --without-media            Export without media (faster, no transcription support)"
    echo "  --debug                    Enable debug output"
    echo "  --wireless-adb IP:PORT     Connect to device via wireless ADB"
    echo ""
    echo "Examples:"
    echo "  # Basic export with full pipeline"
    echo "  docker run --rm --privileged -v /dev/bus/usb:/dev/bus/usb -v ./output:/output whatsapp-export --output /output"
    echo ""
    echo "  # Export with transcriptions but no media in output (RECOMMENDED)"
    echo "  docker run --rm --privileged -v /dev/bus/usb:/dev/bus/usb -v ./output:/output whatsapp-export --output /output --no-output-media"
    echo ""
    echo "  # Export limited chats for testing"
    echo "  docker run --rm --privileged -v /dev/bus/usb:/dev/bus/usb -v ./output:/output whatsapp-export --output /output --limit 5"
    echo ""
    echo "  # Wireless ADB connection"
    echo "  docker run --rm --network=host -v ./output:/output whatsapp-export --output /output --wireless-adb 192.168.1.100:5555"
    exit 0
fi

# Run the whatsapp-export command with all arguments
echo -e "\n${YELLOW}Running WhatsApp export...${NC}"
echo -e "${YELLOW}Command: whatsapp-export $@${NC}\n"

# Execute the command (entry point is now properly installed by pip)
whatsapp-export "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}Export completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "\n${RED}========================================${NC}"
    echo -e "${RED}Export failed with exit code: $EXIT_CODE${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE
