# 🚀 LEHAR CORE - SETUP GUIDE

This guide will help you set up the Lehar Core Platform from scratch.

---

## 📋 PHASE 1: LOCAL DEVELOPMENT SETUP

### Step 1: Install Prerequisites

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3-pip python3-venv postgresql postgresql-contrib
```

**On macOS:**
```bash
brew install python@3.11 postgresql
```

**On Windows:**
- Install Python 3.11 from python.org
- Install PostgreSQL from postgresql.org

### Step 2: Setup PostgreSQL Database

```bash
# Start PostgreSQL service
sudo service postgresql start

# Create database user
sudo -u postgres createuser --interactive --pwprompt
# Enter username: lehar_user
# Enter password: (choose a secure password)
# Superuser? n
# Create databases? y
# Create roles? n

# Create development database
sudo -u postgres createdb -O lehar_user lehar_core_dev
```

### Step 3: Configure Environment Variables

```bash
cd /home/claude/lehar-core-prod/backend

# Copy environment template
cp ../.env.example .env

# Edit the .env file
nano .env
```

**Update these values:**
```
DATABASE_URL=postgresql://lehar_user:YOUR_PASSWORD@localhost:5432/lehar_core_dev
SECRET_KEY=generate-a-random-secret-key-here
JWT_SECRET_KEY=generate-another-random-key-here
MAIL_USERNAME=your-gmail@gmail.com
MAIL_PASSWORD=your-gmail-app-password
```

**To generate secret keys:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 4: Install Python Dependencies

```bash
cd /home/claude/lehar-core-prod/backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 5: Initialize Database

```bash
# Still in backend/ directory with venv activated

# Initialize Flask-Migrate
export FLASK_APP=main.py
flask db init

# Create initial migration
flask db migrate -m "Initial database schema"

# Apply migrations to database
flask db upgrade
```

### Step 6: Run Development Server

```bash
python main.py
```

✅ **Server should now be running at http://localhost:8080**

Test it:
```bash
curl http://localhost:8080/health
# Should return: {"status": "healthy"}
```

---

## 📧 PHASE 2: EMAIL CONFIGURATION

### Option 1: Gmail SMTP (Recommended for testing)

1. **Enable 2-Factor Authentication:**
   - Go to https://myaccount.google.com/security
   - Enable 2-Step Verification

2. **Generate App Password:**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the 16-character password

3. **Update .env:**
   ```
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx  # The app password
   ```

### Option 2: SendGrid (Recommended for production)

```bash
# Install SendGrid
pip install sendgrid

# Update .env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
```

---

## ☁️ PHASE 3: GOOGLE CLOUD SETUP

### Step 1: Create GCP Project

```bash
# Install Google Cloud SDK if not already installed
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize gcloud
gcloud init

# Create new project
gcloud projects create lehar-core-prod --name="Lehar Core Platform"

# Set as active project
gcloud config set project lehar-core-prod

# Enable billing (required for Cloud Run and Cloud SQL)
# Go to: https://console.cloud.google.com/billing
```

### Step 2: Enable Required APIs

```bash
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    storage-api.googleapis.com \
    secretmanager.googleapis.com
```

### Step 3: Create Cloud SQL Instance

```bash
# Create PostgreSQL instance
gcloud sql instances create lehar-core-db \
    --database-version=POSTGRES_14 \
    --tier=db-f1-micro \
    --region=asia-south1 \
    --root-password=YOUR_SECURE_PASSWORD

# Create production database
gcloud sql databases create lehar_core_prod \
    --instance=lehar-core-db

# Create database user
gcloud sql users create lehar_user \
    --instance=lehar-core-db \
    --password=YOUR_USER_PASSWORD
```

**Get Cloud SQL connection name:**
```bash
gcloud sql instances describe lehar-core-db --format="value(connectionName)"
# Output format: PROJECT_ID:REGION:INSTANCE_NAME
```

### Step 4: Create Cloud Storage Bucket

```bash
# Create bucket for organization data
gsutil mb -l asia-south1 gs://lehar-core-prod

# Set lifecycle rules (optional)
cat > lifecycle.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF

gsutil lifecycle set lifecycle.json gs://lehar-core-prod
```

### Step 5: Store Secrets in Secret Manager

```bash
# Create secrets
echo -n "your-production-secret-key" | gcloud secrets create SECRET_KEY --data-file=-
echo -n "your-jwt-secret-key" | gcloud secrets create JWT_SECRET_KEY --data-file=-
echo -n "your-mail-username" | gcloud secrets create MAIL_USERNAME --data-file=-
echo -n "your-mail-password" | gcloud secrets create MAIL_PASSWORD --data-file=-

# Database URL with Cloud SQL connection
echo -n "postgresql://lehar_user:PASSWORD@/lehar_core_prod?host=/cloudsql/PROJECT_ID:REGION:lehar-core-db" | \
    gcloud secrets create DATABASE_URL --data-file=-
```

---

## 🐳 PHASE 4: DEPLOYMENT TO CLOUD RUN

### Option 1: Automated Deployment Script

```bash
cd /home/claude/lehar-core-prod

# Make script executable
chmod +x scripts/deploy.sh

# Run deployment
./scripts/deploy.sh
```

### Option 2: Manual Deployment

```bash
cd /home/claude/lehar-core-prod

# Set project ID
export PROJECT_ID=$(gcloud config get-value project)

# Build Docker image
docker build -t gcr.io/$PROJECT_ID/lehar-core-app:latest -f deployment/Dockerfile .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/lehar-core-app:latest

# Deploy to Cloud Run
gcloud run deploy lehar-core-app \
    --image gcr.io/$PROJECT_ID/lehar-core-app:latest \
    --region asia-south1 \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "FLASK_ENV=production" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,SECRET_KEY=SECRET_KEY:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,MAIL_USERNAME=MAIL_USERNAME:latest,MAIL_PASSWORD=MAIL_PASSWORD:latest" \
    --add-cloudsql-instances PROJECT_ID:asia-south1:lehar-core-db \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10
```

### Step 2: Run Database Migrations on Production

```bash
# Connect to Cloud SQL
gcloud sql connect lehar-core-db --user=lehar_user

# Inside PostgreSQL shell:
\c lehar_core_prod

# Exit and run migrations via Cloud Shell or local with Cloud SQL proxy
```

### Step 3: Test Deployment

```bash
# Get service URL
gcloud run services describe lehar-core-app \
    --region=asia-south1 \
    --format='value(status.url)'

# Test health endpoint
curl https://YOUR-SERVICE-URL/health
```

---

## 🔧 PHASE 5: POST-DEPLOYMENT

### 1. Configure Custom Domain (Optional)

```bash
gcloud run domain-mappings create \
    --service lehar-core-app \
    --domain your-domain.com \
    --region asia-south1
```

### 2. Set Up Monitoring

```bash
# Enable Cloud Logging
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=lehar-core-app" --limit 50
```

### 3. Configure Backup

```bash
# Create backup schedule for Cloud SQL
gcloud sql backups create \
    --instance=lehar-core-db \
    --description="Manual backup before major update"
```

---

## ✅ VERIFICATION CHECKLIST

- [ ] Local development server runs successfully
- [ ] Can create organization and admin user
- [ ] Email verification works
- [ ] Login authentication works
- [ ] JWT tokens are generated correctly
- [ ] Cloud SQL instance is running
- [ ] Cloud Storage bucket exists
- [ ] Secrets are stored in Secret Manager
- [ ] Application deployed to Cloud Run
- [ ] Production health check passes
- [ ] Can access deployed application via URL

---

## 🐛 TROUBLESHOOTING

### Issue: Database connection failed

**Solution:**
```bash
# Check PostgreSQL is running
sudo service postgresql status

# Check database exists
psql -U lehar_user -d lehar_core_dev -c "\l"

# Verify connection string in .env
cat .env | grep DATABASE_URL
```

### Issue: Email not sending

**Solution:**
- Verify SMTP credentials
- Check if port 587 is open
- Test with a simple Python script:
```python
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your-email@gmail.com', 'your-app-password')
```

### Issue: Cloud Run deployment fails

**Solution:**
```bash
# Check Cloud Build logs
gcloud builds list --limit=5

# View detailed logs
gcloud builds log BUILD_ID

# Check Cloud Run logs
gcloud run logs read lehar-core-app --region=asia-south1 --limit=50
```

---

## 📚 NEXT STEPS

1. **Add More Templates**: Create remaining dashboard templates
2. **Implement File Upload**: Add file upload to GCS buckets
3. **Add More Modules**: Build HR, Inventory, Production modules
4. **Testing**: Write unit and integration tests
5. **Documentation**: Add API documentation with Swagger
6. **CI/CD**: Set up automated testing and deployment

---

## 📞 SUPPORT

For questions or issues:
- Email: support@leharcore.com
- Documentation: README.md
- Architecture Document: See uploaded reference document

---

**Last Updated**: January 30, 2026
