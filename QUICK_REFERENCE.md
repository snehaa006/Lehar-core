# ⚡ LEHAR CORE - QUICK REFERENCE

## 🚀 QUICK START COMMANDS

### Local Development Setup (3 minutes)
```bash
# 1. Setup database
sudo -u postgres createdb lehar_core_dev

# 2. Configure environment
cd backend
cp ../.env.example .env
# Edit .env with your credentials

# 3. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Initialize database
export FLASK_APP=main.py
flask db init
flask db migrate -m "Initial schema"
flask db upgrade

# 5. Run server
python main.py
# Access: http://localhost:8080
```

---

## 🐳 DOCKER COMMANDS

```bash
# Build image
docker build -t lehar-core-app -f deployment/Dockerfile .

# Run container
docker run -p 8080:8080 --env-file .env lehar-core-app

# View logs
docker logs -f <container_id>
```

---

## ☁️ GOOGLE CLOUD COMMANDS

### Setup
```bash
# Set project
gcloud config set project lehar-core-prod

# Enable APIs
gcloud services enable run.googleapis.com sqladmin.googleapis.com storage-api.googleapis.com

# Create Cloud SQL
gcloud sql instances create lehar-core-db \
    --database-version=POSTGRES_14 \
    --tier=db-f1-micro \
    --region=asia-south1

# Create bucket
gsutil mb -l asia-south1 gs://lehar-core-prod
```

### Deploy
```bash
# Quick deploy
./scripts/deploy.sh

# Manual deploy
gcloud run deploy lehar-core-app \
    --image gcr.io/PROJECT_ID/lehar-core-app \
    --region asia-south1 \
    --allow-unauthenticated
```

---

## 🗄️ DATABASE COMMANDS

```bash
# Connect to local database
psql -U lehar_user -d lehar_core_dev

# Create migration
flask db migrate -m "Add new field"

# Apply migration
flask db upgrade

# Rollback migration
flask db downgrade

# Connect to Cloud SQL
gcloud sql connect lehar-core-db --user=postgres
```

---

## 📧 TEST EMAIL LOCALLY

```python
from app.utils import send_verification_email

send_verification_email(
    user_email="test@example.com",
    user_name="Test User",
    verification_token="test-token-123"
)
```

---

## 🔑 GENERATE SECRET KEYS

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 🧪 TESTING API ENDPOINTS

### Signup
```bash
curl -X POST http://localhost:8080/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Test Corp",
    "name": "John Doe",
    "email": "john@testcorp.com",
    "password": "SecurePass123"
  }'
```

### Login
```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@testcorp.com",
    "password": "SecurePass123"
  }'
```

### Access Protected Route
```bash
curl http://localhost:8080/dashboard \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 📊 MONITORING

```bash
# View Cloud Run logs
gcloud run logs read lehar-core-app --region=asia-south1

# Stream logs in real-time
gcloud run logs tail lehar-core-app --region=asia-south1

# Check service status
gcloud run services describe lehar-core-app --region=asia-south1
```

---

## 🛠️ TROUBLESHOOTING

### Database Connection Error
```bash
# Check PostgreSQL status
sudo service postgresql status

# Restart PostgreSQL
sudo service postgresql restart

# Test connection
psql -U lehar_user -d lehar_core_dev -c "SELECT 1;"
```

### Port Already in Use
```bash
# Find process using port 8080
lsof -i :8080

# Kill process
kill -9 <PID>
```

### Migration Issues
```bash
# Reset migrations
rm -rf migrations/
flask db init
flask db migrate -m "Initial schema"
flask db upgrade
```

---

## 📦 PROJECT STRUCTURE

```
lehar-core-prod/
├── backend/
│   ├── app/
│   │   ├── models/          # Database models
│   │   ├── blueprints/      # Routes
│   │   ├── services/        # Business logic
│   │   ├── utils/           # Helpers
│   │   └── templates/       # HTML
│   ├── config/              # Configuration
│   └── main.py              # Entry point
├── deployment/
│   ├── Dockerfile
│   └── cloudbuild.yaml
└── scripts/
    └── deploy.sh
```

---

## 🔗 IMPORTANT URLs

### Development
- App: http://localhost:8080
- Health: http://localhost:8080/health
- Signup: http://localhost:8080/auth/signup
- Login: http://localhost:8080/auth/login

### Production
- Get URL: `gcloud run services describe lehar-core-app --region=asia-south1 --format='value(status.url)'`

---

## 📝 ENVIRONMENT VARIABLES

```env
# Required
DATABASE_URL=postgresql://user:pass@host:5432/db
SECRET_KEY=<random-key>
JWT_SECRET_KEY=<random-key>
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# Optional
FLASK_ENV=development
GCS_PROJECT_ID=your-project
GCS_BUCKET_NAME=lehar-core-prod
FRONTEND_URL=http://localhost:8080
```

---

## 🎯 NEXT STEPS AFTER SETUP

1. ✅ Test signup flow
2. ✅ Test email verification
3. ✅ Test login
4. ✅ Test dashboard access
5. ✅ Test invitation system
6. ⏭️ Add more dashboard templates
7. ⏭️ Implement file upload to GCS
8. ⏭️ Build additional modules (HR, Inventory)
9. ⏭️ Add comprehensive testing
10. ⏭️ Deploy to production

---

## 📚 DOCUMENTATION FILES

- `README.md` - Overview and main documentation
- `SETUP_GUIDE.md` - Detailed setup instructions
- `ARCHITECTURE.md` - System architecture details
- `QUICK_REFERENCE.md` - This file

---

**Need Help?**
- Check SETUP_GUIDE.md for detailed instructions
- Check ARCHITECTURE.md for system design
- Check README.md for comprehensive documentation
