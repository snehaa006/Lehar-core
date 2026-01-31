#!/bin/bash
# Manual deployment script for Lehar Core Platform to Cloud Run

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Lehar Core - Cloud Run Deployment${NC}"
echo -e "${GREEN}=====================================${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Get project ID
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No GCP project configured${NC}"
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${YELLOW}Project ID: $PROJECT_ID${NC}"

# Configuration
REGION="asia-south1"
SERVICE_NAME="lehar-core-app"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Step 1: Build Docker image
echo -e "${GREEN}Step 1: Building Docker image...${NC}"
docker build -t $IMAGE_NAME:latest -f deployment/Dockerfile .

# Step 2: Push to Container Registry
echo -e "${GREEN}Step 2: Pushing image to Container Registry...${NC}"
docker push $IMAGE_NAME:latest

# Step 3: Deploy to Cloud Run
echo -e "${GREEN}Step 3: Deploying to Cloud Run...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME:latest \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "FLASK_ENV=production,GCS_PROJECT_ID=$PROJECT_ID,GCS_BUCKET_NAME=lehar-core-prod" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,SECRET_KEY=SECRET_KEY:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,MAIL_USERNAME=MAIL_USERNAME:latest,MAIL_PASSWORD=MAIL_PASSWORD:latest" \
    --min-instances 0 \
    --max-instances 10 \
    --memory 512Mi \
    --cpu 1

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}Deployment Successful!${NC}"
echo -e "${GREEN}=====================================${NC}"
echo -e "${YELLOW}Service URL: $SERVICE_URL${NC}"
echo -e "${YELLOW}Health Check: $SERVICE_URL/health${NC}"
echo ""
echo "Next steps:"
echo "1. Test the health endpoint"
echo "2. Configure your domain (if needed)"
echo "3. Set up Cloud SQL connection"
echo "4. Run database migrations"
