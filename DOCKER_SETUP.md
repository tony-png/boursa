# Docker Setup for TWS APIs

## Prerequisites

1. **Docker Desktop** (for Windows/Mac) or Docker Engine (for Linux)
2. **Interactive Brokers TWS or IB Gateway** running on port 7497
3. **Environment files** configured in both API directories

## Local Testing Instructions

### 1. Prepare Environment Files

Make sure you have `.env` files in both directories:

```bash
# Copy example files if not already done
cp tws-data-api-v2/.env.example tws-data-api-v2/.env
cp tws-orders-api-v2/.env.example tws-orders-api-v2/.env
```

Edit the `.env` files to match your TWS configuration.

### 2. Start Docker Desktop (Windows/Mac)

Make sure Docker Desktop is running before proceeding.

### 3. Build and Run Services

```bash
# Build both services
docker-compose build

# Or build without cache (for clean build)
docker-compose build --no-cache

# Start services in detached mode
docker-compose up -d

# Or start with logs visible
docker-compose up
```

### 4. Verify Services

Check that both services are running:

```bash
# Check container status
docker-compose ps

# Check health endpoints
curl http://localhost:8000/health  # Data API
curl http://localhost:8001/health  # Orders API

# View logs
docker-compose logs -f tws-data-api
docker-compose logs -f tws-orders-api
```

### 5. Test API Endpoints

```bash
# Test Data API
curl http://localhost:8000/stock/AAPL
curl http://localhost:8000/stocks?symbols=AAPL,MSFT,GOOGL

# Test Orders API
curl http://localhost:8001/api/v1/orders
curl http://localhost:8001/api/v1/positions
```

## Managing Services

### Stop Services
```bash
docker-compose down
```

### Restart Services
```bash
docker-compose restart
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f tws-data-api
docker-compose logs -f tws-orders-api
```

### Rebuild After Code Changes
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## Deployment to Debian Server

### 1. Initial Server Setup

On your Debian server:

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add your user to docker group
sudo usermod -aG docker $USER
# Log out and back in for this to take effect
```

### 2. Setup Git Repository

First, push your code to GitHub/GitLab:

```bash
git init
git add .
git commit -m "Initial Docker setup for TWS APIs"
git remote add origin https://github.com/yourusername/boursa.git
git push -u origin main
```

### 3. Deploy Using Script

Update the `deploy.sh` script with your server details:

```bash
# Edit deploy.sh and update these variables:
REMOTE_USER="your-username"
REMOTE_HOST="your-server-ip"
GIT_REPO="https://github.com/yourusername/boursa.git"
```

Then deploy:

```bash
# Make script executable
chmod +x deploy.sh

# Full deployment (push to git + deploy)
./deploy.sh full

# Or just deploy without pushing
./deploy.sh deploy

# Check status
./deploy.sh status

# View logs
./deploy.sh logs
```

### 4. Manual Deployment

If you prefer manual deployment:

```bash
# SSH to your server
ssh user@your-server-ip

# Clone repository
git clone https://github.com/yourusername/boursa.git
cd boursa

# Setup environment files
cp tws-data-api-v2/.env.example tws-data-api-v2/.env
cp tws-orders-api-v2/.env.example tws-orders-api-v2/.env
# Edit .env files with production values

# Build and start
docker-compose build
docker-compose up -d

# Check status
docker-compose ps
curl http://localhost:8000/health
curl http://localhost:8001/health
```

## Important Notes

### TWS Connection

- On **Windows/Mac** with Docker Desktop, the containers use `host.docker.internal` to connect to TWS on your host machine
- On **Linux**, you may need to use `--network host` or the actual host IP address
- Ensure TWS/IB Gateway is configured to accept connections from localhost

### Environment Variables

The docker-compose.yml overrides certain environment variables:
- `API_HOST=0.0.0.0` (to bind to all interfaces in container)
- `TWS_HOST=host.docker.internal` (to connect to host TWS)

You can modify these in docker-compose.yml if needed.

### Security Considerations

For production:
1. Use proper secrets management (Docker secrets or external vault)
2. Don't commit `.env` files to git
3. Use HTTPS with proper certificates
4. Implement proper firewall rules
5. Consider using Docker Swarm or Kubernetes for orchestration

## Troubleshooting

### Docker not running
```
Error: Cannot connect to the Docker daemon
```
**Solution**: Start Docker Desktop (Windows/Mac) or Docker service (Linux)

### TWS connection failed
```
Error: Could not connect to TWS
```
**Solution**:
- Ensure TWS/IB Gateway is running
- Check TWS is configured to accept API connections
- Verify port 7497 (paper) or 7496 (live) is correct
- Check firewall settings

### Port already in use
```
Error: bind: address already in use
```
**Solution**:
- Stop any locally running instances of the APIs
- Or change ports in docker-compose.yml

### Permission denied
```
Error: permission denied while trying to connect to the Docker daemon
```
**Solution**:
- Linux: Add user to docker group: `sudo usermod -aG docker $USER`
- Then log out and back in

## Next Steps

1. Test locally with Docker
2. Setup GitHub/GitLab repository
3. Configure production `.env` files
4. Deploy to Debian server
5. Setup monitoring and logging
6. Configure automatic backups
7. Implement CI/CD pipeline (optional)