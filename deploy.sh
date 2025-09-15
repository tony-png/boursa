#!/bin/bash

# TWS APIs Docker Deployment Script
# This script helps deploy updates from your laptop to the Debian server

set -e  # Exit on error

# Configuration
REMOTE_USER="your-username"
REMOTE_HOST="your-server-ip"
REMOTE_DIR="/home/${REMOTE_USER}/boursa"
GIT_REPO="https://github.com/your-username/boursa.git"  # Update with your repo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}TWS APIs Deployment Script${NC}"
echo "=============================="

# Function to display usage
usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  local    - Build and run locally"
    echo "  push     - Push changes to git repository"
    echo "  deploy   - Deploy to remote server"
    echo "  full     - Full deployment (push + deploy)"
    echo "  logs     - Show remote logs"
    echo "  status   - Check remote status"
    echo "  restart  - Restart remote services"
    echo "  stop     - Stop remote services"
    echo ""
    exit 1
}

# Build and run locally
local_build() {
    echo -e "${YELLOW}Building and starting services locally...${NC}"
    docker-compose down
    docker-compose build --no-cache
    docker-compose up -d
    echo -e "${GREEN}Services started locally${NC}"
    echo "Data API: http://localhost:8000"
    echo "Orders API: http://localhost:8001"
    docker-compose ps
}

# Push to git repository
push_to_git() {
    echo -e "${YELLOW}Pushing changes to git repository...${NC}"
    git add .
    echo "Enter commit message: "
    read commit_msg
    git commit -m "$commit_msg"
    git push origin main  # Adjust branch name if needed
    echo -e "${GREEN}Changes pushed to repository${NC}"
}

# Deploy to remote server
deploy_to_server() {
    echo -e "${YELLOW}Deploying to remote server ${REMOTE_HOST}...${NC}"

    # SSH commands to execute on remote server
    ssh ${REMOTE_USER}@${REMOTE_HOST} << EOF
        set -e

        # Create directory if it doesn't exist
        mkdir -p ${REMOTE_DIR}
        cd ${REMOTE_DIR}

        # Clone or pull latest changes
        if [ ! -d ".git" ]; then
            echo "Cloning repository..."
            git clone ${GIT_REPO} .
        else
            echo "Pulling latest changes..."
            git pull origin main
        fi

        # Copy environment files if they don't exist
        if [ ! -f "tws-data-api-v2/.env" ]; then
            cp tws-data-api-v2/.env.example tws-data-api-v2/.env
            echo "Created tws-data-api-v2/.env - Please update with production values"
        fi

        if [ ! -f "tws-orders-api-v2/.env" ]; then
            cp tws-orders-api-v2/.env.example tws-orders-api-v2/.env
            echo "Created tws-orders-api-v2/.env - Please update with production values"
        fi

        # Stop existing containers
        docker-compose down || true

        # Build and start new containers
        docker-compose build --no-cache
        docker-compose up -d

        # Show status
        docker-compose ps

        echo "Deployment complete!"
EOF

    echo -e "${GREEN}Deployment successful!${NC}"
}

# Show remote logs
show_logs() {
    echo -e "${YELLOW}Fetching logs from remote server...${NC}"
    ssh ${REMOTE_USER}@${REMOTE_HOST} "cd ${REMOTE_DIR} && docker-compose logs --tail=100 -f"
}

# Check remote status
check_status() {
    echo -e "${YELLOW}Checking status on remote server...${NC}"
    ssh ${REMOTE_USER}@${REMOTE_HOST} << EOF
        cd ${REMOTE_DIR}
        echo "Container Status:"
        docker-compose ps
        echo ""
        echo "Health Check - Data API:"
        curl -s http://localhost:8000/health | python3 -m json.tool || echo "Data API not responding"
        echo ""
        echo "Health Check - Orders API:"
        curl -s http://localhost:8001/health | python3 -m json.tool || echo "Orders API not responding"
EOF
}

# Restart remote services
restart_services() {
    echo -e "${YELLOW}Restarting services on remote server...${NC}"
    ssh ${REMOTE_USER}@${REMOTE_HOST} "cd ${REMOTE_DIR} && docker-compose restart"
    echo -e "${GREEN}Services restarted${NC}"
}

# Stop remote services
stop_services() {
    echo -e "${YELLOW}Stopping services on remote server...${NC}"
    ssh ${REMOTE_USER}@${REMOTE_HOST} "cd ${REMOTE_DIR} && docker-compose down"
    echo -e "${GREEN}Services stopped${NC}"
}

# Main script logic
case "$1" in
    local)
        local_build
        ;;
    push)
        push_to_git
        ;;
    deploy)
        deploy_to_server
        ;;
    full)
        push_to_git
        deploy_to_server
        ;;
    logs)
        show_logs
        ;;
    status)
        check_status
        ;;
    restart)
        restart_services
        ;;
    stop)
        stop_services
        ;;
    *)
        usage
        ;;
esac