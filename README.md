# Lehar Core Platform

Multi-tenant SaaS platform for industrial ERP with organization-level authentication and role-based access control.

## 🏗️ Architecture

- **Backend**: Flask (Python)
- **Frontend**: Jinja2 templates + Bootstrap
- **Database**: Cloud SQL (PostgreSQL)
- **Storage**: Google Cloud Storage buckets
- **Deployment**: Google Cloud Run
- **Authentication**: JWT-based

## 📁 Project Structure

```
lehar-core-prod/
├── backend/
│   ├── app/
│   │   ├── models/          # Database models (Organization, User, Invitation)
│   │   ├── blueprints/      # Flask routes (auth, dashboard, invitations)
│   │   ├── services/        # Business logic
│   │   ├── utils/           # Helper functions (JWT, email, validators)
│   │   └── templates/       # HTML templates
│   ├── config/              # Configuration files
│   ├── migrations/          # Database migrations
│   ├── main.py              # Application entry point
│   └── requirements.txt     # Python dependencies
├── deployment/
│   ├── Dockerfile           # Container definition
│   └── cloudbuild.yaml      # Cloud Build config
└── scripts/
    └── deploy.sh            # Deployment script
```

## 🚀 Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- PostgreSQL
- Google Cloud SDK (for deployment)

### 1. Clone and Setup

```bash
cd lehar-core-prod/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp ../.env.example .env

# Edit .env with your settings
nano .env
```

**Required settings:**
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Flask secret key
- `JWT_SECRET_KEY`: JWT signing key
- `MAIL_USERNAME` & `MAIL_PASSWORD`: SMTP credentials

### 3. Initialize Database

```bash
# Create database
createdb lehar_core_dev

# Run migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 4. Run Development Server

```bash
python main.py
```

Server will start at `http://localhost:8080`

## 🗄️ Database Setup (Cloud SQL)

### Create Cloud SQL Instance

```bash
gcloud sql instances create lehar-core-db \
    --database-version=POSTGRES_14 \
    --tier=db-f1-micro \
    --region=asia-south1
```

### Create Database

```bash
gcloud sql databases create lehar_core_prod \
    --instance=lehar-core-db
```

### Set User Password

```bash
gcloud sql users set-password postgres \
    --instance=lehar-core-db \
    --password=YOUR_SECURE_PASSWORD
```

## 📦 Google Cloud Storage Setup

### Create Bucket

```bash
gsutil mb -l asia-south1 gs://lehar-core-prod
```

### Set Bucket Permissions

```bash
gsutil iam ch allUsers:objectViewer gs://lehar-core-prod
```

## 🐳 Deployment to Cloud Run

### Option 1: Using Deployment Script

```bash
cd /path/to/lehar-core-prod
./scripts/deploy.sh
```

### Option 2: Manual Deployment

```bash
# Build and push image
docker build -t gcr.io/YOUR_PROJECT_ID/lehar-core-app -f deployment/Dockerfile .
docker push gcr.io/YOUR_PROJECT_ID/lehar-core-app

# Deploy to Cloud Run
gcloud run deploy lehar-core-app \
    --image gcr.io/YOUR_PROJECT_ID/lehar-core-app \
    --region asia-south1 \
    --platform managed \
    --allow-unauthenticated
```

### Option 3: Automated CI/CD

```bash
# Set up Cloud Build trigger
gcloud builds submit --config=deployment/cloudbuild.yaml
```

## 🔐 Environment Variables for Production

Store secrets in Google Secret Manager:

```bash
# Create secrets
echo -n "your-secret-key" | gcloud secrets create SECRET_KEY --data-file=-
echo -n "your-jwt-secret" | gcloud secrets create JWT_SECRET_KEY --data-file=-
echo -n "postgresql://user:pass@host/db" | gcloud secrets create DATABASE_URL --data-file=-
```

## 📧 Email Configuration

### Using Gmail SMTP

1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the app password in `MAIL_PASSWORD` environment variable

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app tests/
```

## 📋 User Roles & Permissions

| Role | Permissions |
|------|-------------|
| **Super Admin** | Billing, add/remove users, assign roles, all modules |
| **Admin** | Manage modules, view reports |
| **Manager** | Use operational modules |
| **HR User** | Only HR module |
| **Viewer** | Read-only dashboards |

## 💰 Subscription Plans

| Plan | Users | Modules |
|------|-------|---------|
| **Free** | 3 | HR + Basic Dashboard |
| **Starter** | 10 | HR + Inventory |
| **Pro** | 25 | + Production Planning |
| **Enterprise** | Unlimited | Full IIoT + Press Monitoring |

## 🔗 API Endpoints

### Authentication
- `POST /auth/signup` - Register organization
- `POST /auth/login` - User login
- `GET /auth/verify-email?token=` - Verify email
- `POST /auth/check-domain` - Check if domain exists

### Dashboard
- `GET /dashboard/` - Main dashboard (role-based)
- `GET /dashboard/profile` - User profile
- `GET /dashboard/organization` - Organization settings

### Invitations
- `POST /invitations/send` - Send user invitation
- `GET /invitations/accept?token=` - Accept invitation
- `GET /invitations/list` - List invitations

## 🛠️ Database Migrations

```bash
# Create new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback migration
flask db downgrade
```

## 📊 Monitoring

### Health Check
```
GET /health
```

### Cloud Run Logs
```bash
gcloud run logs read lehar-core-app --region=asia-south1
```

## 🔧 Troubleshooting

### Database Connection Issues
- Verify Cloud SQL instance is running
- Check connection string format
- Ensure Cloud SQL Proxy is configured

### Email Not Sending
- Verify SMTP credentials
- Check firewall rules for port 587
- Ensure "Less Secure Apps" is enabled (for Gmail)

## 📝 License

© 2026 Lehar Core Platform. All rights reserved.

## 👥 Support

For support, contact: support@leharcore.com
# Lehar-core
