#!/usr/bin/env bash
# Setup & Prerequisite Bootstrap Script for Zammad CLI Controller
# Supports Ubuntu and macOS

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse options
CUSTOM_ENV_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --env-file)
            CUSTOM_ENV_FILE="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: ./install.sh [--env-file <custom-env-file-path>]"
            exit 1
            ;;
    esac
done

# ==============================================================================
# CONFIGURATION VARIABLES (Edit here to change dependencies / requirements)
# ==============================================================================
APT_PACKAGES="python3 curl gnupg lsb-release wget openssl git"
REQUIRED_VM_MAX_MAP_COUNT=262144
# ==============================================================================

# Setup Log Directory and File
OS_TYPE="$(uname -s)"
if [ "$OS_TYPE" = "Linux" ]; then
    LOG_DIR="/opt/zammad-docker"
else
    # On macOS or developer directory
    LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/zammad-install.log"

# Initialize log file
echo -e "\n--- Zammad Bootstrap Installation started at $(date) ---" >> "$LOG_FILE"

# Initialize step statuses
OS_CHECK="PENDING"
KERNEL_CHECK="PENDING"
PYTHON_CHECK="PENDING"
DOCKER_CHECK="PENDING"
DAEMON_CHECK="PENDING"
ZAMMAD_INSTALL="PENDING"
SYMLINK_CHECK="PENDING"

print_bootstrap_summary() {
    echo -e "\n${GREEN}================================================================${NC}"
    echo -e "${GREEN}      Zammad Helpdesk Bootstrap Setup Summary                   ${NC}"
    echo -e "================================================================"
    
    print_step_line() {
        local step_name="$1"
        local status="$2"
        local color=""
        if [ "$status" = "SUCCESS" ]; then
            color="${GREEN}"
        elif [ "$status" = "SKIPPED" ]; then
            color="${YELLOW}"
        elif [ "$status" = "FAILED" ]; then
            color="${RED}"
        else
            color="${NC}"
        fi
        printf "  [%b%-7s%b] %s\n" "${color}" "${status}" "${NC}" "${step_name}"
    }

    print_step_line "OS Compatibility Check" "$OS_CHECK"
    print_step_line "Linux Kernel Memory Tuning" "$KERNEL_CHECK"
    print_step_line "Verify Python 3 Presence" "$PYTHON_CHECK"
    print_step_line "Install/Verify Docker Engine" "$DOCKER_CHECK"
    print_step_line "Verify Docker Daemon Health" "$DAEMON_CHECK"
    print_step_line "Invoke Python Zammad Installer" "$ZAMMAD_INSTALL"
    print_step_line "Create Global CLI Symlink" "$SYMLINK_CHECK"
    
    echo -e "================================================================"
    echo -e "Detailed logs are available at: ${BLUE}${LOG_FILE}${NC}"
    echo -e "================================================================"
}

echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}      Zammad Helpdesk Installer & CLI Bootstrapper              ${NC}"
echo -e "      Saving logs to: ${BLUE}${LOG_FILE}${NC}"
echo -e "${GREEN}================================================================${NC}"

# 1. Detect and Check OS compatibility
if [ "$OS_TYPE" = "Linux" ]; then
    if [ ! -f /etc/debian_version ]; then
        echo -e "${RED}Error: Linux support is optimized for Ubuntu/Debian.${NC}" | tee -a "$LOG_FILE"
        OS_CHECK="FAILED"
        print_bootstrap_summary
        exit 1
    fi
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Error: On Linux/Ubuntu, this script must be run as root or via sudo.${NC}" | tee -a "$LOG_FILE"
        echo -e "Usage: sudo ./install.sh"
        OS_CHECK="FAILED"
        print_bootstrap_summary
        exit 1
    fi
    OS_CHECK="SUCCESS"

    # Kernel Tuning (Elasticsearch Hard Requirement)
    echo -e "\n${YELLOW}Configuring Linux kernel parameter: vm.max_map_count for Elasticsearch...${NC}" | tee -a "$LOG_FILE"
    if sysctl -w vm.max_map_count=${REQUIRED_VM_MAX_MAP_COUNT} 2>&1 | tee -a "$LOG_FILE"; then
        if ! grep -q "vm.max_map_count=${REQUIRED_VM_MAX_MAP_COUNT}" /etc/sysctl.conf; then
            echo "vm.max_map_count=${REQUIRED_VM_MAX_MAP_COUNT}" >> /etc/sysctl.conf
        fi
        KERNEL_CHECK="SUCCESS"
    else
        KERNEL_CHECK="FAILED"
    fi

    # Verify/Install Python 3
    echo -e "\n${YELLOW}[1/4] Checking Python 3...${NC}" | tee -a "$LOG_FILE"
    if apt-get update -y 2>&1 | tee -a "$LOG_FILE" && apt-get install -y ${APT_PACKAGES} 2>&1 | tee -a "$LOG_FILE"; then
        if command -v python3 &> /dev/null; then
            PYTHON_CHECK="SUCCESS"
        else
            PYTHON_CHECK="FAILED"
            echo -e "${RED}Error: Python 3 was not found on path after installation package ran.${NC}" | tee -a "$LOG_FILE"
            print_bootstrap_summary
            exit 1
        fi
    else
        PYTHON_CHECK="FAILED"
        echo -e "${RED}Error: Failed to install Python 3 or core dependencies.${NC}" | tee -a "$LOG_FILE"
        print_bootstrap_summary
        exit 1
    fi

    # Verify/Install Docker
    if ! command -v docker &> /dev/null; then
        echo -e "\n${YELLOW}[2/4] Docker not detected. Installing Docker Engine...${NC}" | tee -a "$LOG_FILE"
        mkdir -p /etc/apt/keyrings 2>&1 | tee -a "$LOG_FILE"
        rm -f /etc/apt/keyrings/docker.gpg 2>&1 | tee -a "$LOG_FILE"
        if curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>&1 | tee -a "$LOG_FILE"; then
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
              $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        else
            DOCKER_CHECK="FAILED"
            echo -e "${RED}Error: Failed to download Docker repository GPG key.${NC}" | tee -a "$LOG_FILE"
            print_bootstrap_summary
            exit 1
        fi

        apt-get update -y 2>&1 | tee -a "$LOG_FILE"
        if apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin 2>&1 | tee -a "$LOG_FILE"; then
            systemctl enable --now docker 2>&1 | tee -a "$LOG_FILE"
            systemctl enable --now containerd 2>&1 | tee -a "$LOG_FILE"
            
            SUDO_USER_NAME=${SUDO_USER:-}
            if [ -n "$SUDO_USER_NAME" ]; then
                usermod -aG docker "$SUDO_USER_NAME" 2>&1 | tee -a "$LOG_FILE"
            fi
            DOCKER_CHECK="SUCCESS"
        else
            DOCKER_CHECK="FAILED"
            echo -e "${RED}Error: Failed to install Docker Engine packages.${NC}" | tee -a "$LOG_FILE"
            print_bootstrap_summary
            exit 1
        fi
    else
        echo -e "\n${GREEN}[2/4] Docker is already installed.${NC}" | tee -a "$LOG_FILE"
        DOCKER_CHECK="SKIPPED"
    fi

    # Verify Daemon Health
    if docker info &> /dev/null; then
        DAEMON_CHECK="SUCCESS"
    else
        DAEMON_CHECK="FAILED"
        echo -e "${RED}Error: Docker daemon is not running or socket is inaccessible.${NC}" | tee -a "$LOG_FILE"
        print_bootstrap_summary
        exit 1
    fi

elif [ "$OS_TYPE" = "Darwin" ]; then
    OS_CHECK="SUCCESS"
    KERNEL_CHECK="SKIPPED" # Docker Desktop on macOS handles memory parameters internally
    
    # Verify/Install Python 3
    echo -e "\n${YELLOW}[1/4] Checking Python 3...${NC}" | tee -a "$LOG_FILE"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Python 3 is not installed. Requesting Xcode tools...${NC}" | tee -a "$LOG_FILE"
        xcode-select --install || true 2>&1 | tee -a "$LOG_FILE"
        PYTHON_CHECK="FAILED"
        print_bootstrap_summary
        exit 1
    fi
    PYTHON_CHECK="SUCCESS"

    # Verify/Install Docker
    if ! command -v docker &> /dev/null; then
        echo -e "\n${YELLOW}[2/4] Docker CLI not found. Checking Homebrew...${NC}" | tee -a "$LOG_FILE"
        if ! command -v brew &> /dev/null; then
            echo -e "${RED}Error: Homebrew is required to install Docker on macOS.${NC}" | tee -a "$LOG_FILE"
            DOCKER_CHECK="FAILED"
            print_bootstrap_summary
            exit 1
        fi
        if brew install --cask docker 2>&1 | tee -a "$LOG_FILE"; then
            DOCKER_CHECK="SUCCESS"
        else
            DOCKER_CHECK="FAILED"
            echo -e "${RED}Error: Failed to install Docker via Homebrew.${NC}" | tee -a "$LOG_FILE"
            print_bootstrap_summary
            exit 1
        fi
    else
        DOCKER_CHECK="SKIPPED"
    fi

    # Verify Daemon Health
    if ! docker info &> /dev/null; then
        echo -e "\n${YELLOW}[3/4] Launching Docker Desktop...${NC}" | tee -a "$LOG_FILE"
        open -a Docker || true 2>&1 | tee -a "$LOG_FILE"
        echo -e "${YELLOW}Please wait for Docker Desktop to finish launching, then press Enter to continue...${NC}"
        read -r
        if docker info &> /dev/null; then
            DAEMON_CHECK="SUCCESS"
        else
            DAEMON_CHECK="FAILED"
            echo -e "${RED}Error: Docker daemon is not active.${NC}" | tee -a "$LOG_FILE"
            print_bootstrap_summary
            exit 1
        fi
    else
        DAEMON_CHECK="SUCCESS"
    fi

else
    echo -e "${RED}Unsupported OS: $OS_TYPE${NC}" | tee -a "$LOG_FILE"
    OS_CHECK="FAILED"
    print_bootstrap_summary
    exit 1
fi

# Ensure executable wrapper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "${SCRIPT_DIR}/zammad" 2>&1 | tee -a "$LOG_FILE"

# Deploy CLI files to /opt/zammad-docker on Linux so they are globally accessible
if [ "$OS_TYPE" = "Linux" ]; then
    echo -e "\n${YELLOW}Deploying CLI control files to /opt/zammad-docker...${NC}" | tee -a "$LOG_FILE"
    mkdir -p /opt/zammad-docker 2>&1 | tee -a "$LOG_FILE"
    cp -rf "${SCRIPT_DIR}/zammad" "${SCRIPT_DIR}/src" /opt/zammad-docker/ 2>&1 | tee -a "$LOG_FILE"
    chmod +x /opt/zammad-docker/zammad 2>&1 | tee -a "$LOG_FILE"
    RUN_DIR="/opt/zammad-docker"
else
    RUN_DIR="${SCRIPT_DIR}"
fi

# Create global symlink
SYMLINK_CHECK="SKIPPED"
if [ -d /usr/local/bin ] && [ ! -f /usr/local/bin/zammad ]; then
    if [ "$OS_TYPE" = "Linux" ]; then
        if ln -sf "/opt/zammad-docker/zammad" /usr/local/bin/zammad 2>&1 | tee -a "$LOG_FILE"; then
            SYMLINK_CHECK="SUCCESS"
        else
            SYMLINK_CHECK="FAILED"
        fi
    elif [ "$OS_TYPE" = "Darwin" ]; then
        if ln -sf "${SCRIPT_DIR}/zammad" /usr/local/bin/zammad 2>/dev/null; then
            SYMLINK_CHECK="SUCCESS"
        else
            SYMLINK_CHECK="SKIPPED"
        fi
    fi
fi

# Invoke Python Installer
echo -e "\n${YELLOW}[4/4] Invoking Zammad CLI Python Installer...${NC}" | tee -a "$LOG_FILE"
INSTALL_CMD=("${RUN_DIR}/zammad" "install")
if [ -n "$CUSTOM_ENV_FILE" ]; then
    if [[ "$CUSTOM_ENV_FILE" = /* ]]; then
        ABS_ENV_FILE="$CUSTOM_ENV_FILE"
    else
        ABS_ENV_FILE="$(pwd)/$CUSTOM_ENV_FILE"
    fi
    INSTALL_CMD+=("--env-file" "$ABS_ENV_FILE")
    echo "Using custom configuration seed file: $ABS_ENV_FILE" | tee -a "$LOG_FILE"
fi

if "${INSTALL_CMD[@]}"; then
    ZAMMAD_INSTALL="SUCCESS"
else
    ZAMMAD_INSTALL="FAILED"
    echo -e "${RED}Error: Python installer execution failed.${NC}" | tee -a "$LOG_FILE"
    print_bootstrap_summary
    exit 1
fi

# Print final bootstrap report
print_bootstrap_summary

if [ "$SYMLINK_CHECK" = "SKIPPED" ] && [ "$OS_TYPE" = "Darwin" ]; then
    echo -e "\n${YELLOW}Note: To execute 'zammad' from anywhere on your Mac, create the symlink manually:${NC}"
    echo -e "  sudo ln -sf \"${SCRIPT_DIR}/zammad\" /usr/local/bin/zammad"
fi

echo -e "\n${GREEN}Bootstrap Setup Completed Successfully!${NC}\n"