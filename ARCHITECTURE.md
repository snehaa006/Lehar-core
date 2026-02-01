# 🏗️ LEHAR CORE - SYSTEM ARCHITECTURE

## 📊 HIGH-LEVEL ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                           │
│                    (Browser / Mobile App)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ HTTPS
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      GOOGLE CLOUD RUN                            │
│                    (Flask Application)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  FLASK APP LAYERS                         │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐         │  │
│  │  │ Templates  │  │ Blueprints │  │  Services  │         │  │
│  │  │  (Jinja)   │  │  (Routes)  │  │  (Logic)   │         │  │
│  │  └────────────┘  └────────────┘  └────────────┘         │  │
│  │         │               │                │                │  │
│  │         └───────────────┴────────────────┘                │  │
│  │                        │                                   │  │
│  │                        ▼                                   │  │
│  │              ┌──────────────────┐                         │  │
│  │              │  Models (ORM)    │                         │  │
│  │              │  SQLAlchemy      │                         │  │
│  │              └──────────────────┘                         │  │
│  └────────────────────┬───────────────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Cloud SQL   │ │  Cloud       │ │   SMTP       │
│ (PostgreSQL) │ │  Storage     │ │  (Email)     │
│              │ │  Buckets     │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
   Organizations    Org Files       Verification
   Users            Documents       Invitations
   Invitations      Reports         Notifications
```

---

## 🗄️ DATABASE SCHEMA

### **Organizations Table**
```sql
CREATE TABLE organizations (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    domain VARCHAR(255) UNIQUE,
    website VARCHAR(255),
    industry_type VARCHAR(100),
    company_size VARCHAR(50),
    country VARCHAR(100),
    plan_type VARCHAR(20) DEFAULT 'free',
    max_users INTEGER DEFAULT 3,
    is_email_verified BOOLEAN DEFAULT false,
    industrial_verified BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### **Users Table**
```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    role VARCHAR(20) DEFAULT 'viewer',
    job_title VARCHAR(100),
    is_email_verified BOOLEAN DEFAULT false,
    email_verification_token VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_org ON users(organization_id);
```

### **Invitations Table**
```sql
CREATE TABLE invitations (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) REFERENCES organizations(id),
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'viewer',
    token VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    invited_by_user_id VARCHAR(36) REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    accepted_at TIMESTAMP
);

CREATE INDEX idx_invitations_token ON invitations(token);
CREATE INDEX idx_invitations_email ON invitations(email);
```

---

## 🔐 AUTHENTICATION FLOW

### 1. **Organization Signup Flow**

```
User fills signup form
    │
    ├──> Validate input
    │       ├──> Check email format
    │       ├──> Check password strength
    │       └──> Check phone format
    │
    ├──> Check if domain exists
    │       ├──> Work email? Check organization table
    │       ├──> Exists? → Show "Request access"
    │       └──> Not exists? → Continue
    │
    ├──> Create organization record
    │       ├──> Generate slug from company name
    │       ├──> Set plan_type = 'free'
    │       └──> max_users = 3
    │
    ├──> Create admin user
    │       ├──> Hash password
    │       ├──> role = 'super_admin'
    │       ├──> Generate verification token
    │       └──> is_email_verified = false
    │
    ├──> Send verification email
    │       └──> SMTP → verification link
    │
    └──> Redirect to login with success message
```

### 2. **Email Verification Flow**

```
User clicks verification link
    │
    ├──> Extract token from URL
    │
    ├──> Find user by token
    │       └──> Not found? → "Invalid token"
    │
    ├──> Check if already verified
    │       └──> Yes? → "Already verified"
    │
    ├──> Mark user as verified
    │       ├──> is_email_verified = true
    │       ├──> Clear verification token
    │       └──> If super_admin → verify org too
    │
    └──> Redirect to login
```

### 3. **Login Flow**

```
User enters email + password
    │
    ├──> Find user by email
    │       └──> Not found? → "Invalid credentials"
    │
    ├──> Verify password
    │       └──> Wrong? → "Invalid credentials"
    │
    ├──> Check user.is_active
    │       └──> Inactive? → "Account inactive"
    │
    ├──> Check user.is_email_verified
    │       └──> Not verified? → "Verify email first"
    │
    ├──> Check organization.is_active
    │       └──> Inactive? → "Organization inactive"
    │
    ├──> Generate JWT token
    │       ├──> Payload: user_id, org_id, role, plan_type
    │       ├──> Expiry: 24 hours
    │       └──> Sign with JWT_SECRET_KEY
    │
    ├──> Update last_login timestamp
    │
    └──> Return token + redirect to dashboard
```

### 4. **JWT Token Structure**

```json
{
  "user_id": "uuid-user-123",
  "organization_id": "uuid-org-456",
  "role": "super_admin",
  "plan_type": "enterprise",
  "exp": 1738368000,
  "iat": 1738281600
}
```

---

## 👥 USER INVITATION FLOW

```
Admin clicks "Invite User"
    │
    ├──> Check permissions (super_admin or admin only)
    │
    ├──> Check user limit
    │       └──> Limit reached? → "Upgrade plan"
    │
    ├──> Check if email already exists
    │       ├──> In same org? → "Already member"
    │       └──> In other org? → "Has account elsewhere"
    │
    ├──> Check pending invitations
    │       └──> Valid invite exists? → "Already invited"
    │
    ├──> Create invitation record
    │       ├──> Generate unique token
    │       ├──> status = 'pending'
    │       ├──> expires_at = now + 7 days
    │       └──> Store invited_by_user_id
    │
    ├──> Send invitation email
    │       └──> SMTP → Accept invitation link
    │
    └──> Show success message

─────────────────────────────

Invitee clicks invitation link
    │
    ├──> Extract token from URL
    │
    ├──> Find invitation by token
    │       └──> Not found? → "Invalid invitation"
    │
    ├──> Check if valid
    │       ├──> status != 'pending'? → "Already used"
    │       └──> expired? → "Invitation expired"
    │
    ├──> Show "Set Password" form
    │
    ├──> User submits password
    │
    ├──> Create user account
    │       ├──> organization_id from invitation
    │       ├──> role from invitation
    │       ├──> is_email_verified = true (auto)
    │       └──> is_active = true
    │
    ├──> Update invitation
    │       ├──> status = 'accepted'
    │       └──> accepted_at = now
    │
    └──> Redirect to login
```

---

## 🎭 ROLE-BASED ACCESS CONTROL

### **Role Hierarchy**

```
Super Admin  ────────> Full control
    │
    ├─> Billing
    ├─> Add/remove users
    ├─> Assign roles
    └─> All modules

Admin  ──────────────> Management access
    │
    ├─> Manage modules
    ├─> View reports
    └─> Invite users

Manager  ────────────> Operational access
    │
    ├─> Use operational modules
    └─> Create reports

HR User  ────────────> HR module only
    │
    └─> HR management

Viewer  ─────────────> Read-only
    │
    └─> Dashboards only
```

### **Module Access Matrix**

| Module | Free | Starter | Pro | Enterprise |
|--------|------|---------|-----|------------|
| HR | ✅ | ✅ | ✅ | ✅ |
| Basic Dashboard | ✅ | ✅ | ✅ | ✅ |
| Inventory | ❌ | ✅ | ✅ | ✅ |
| Production Planning | ❌ | ❌ | ✅ | ✅ |
| Press Monitoring | ❌ | ❌ | ❌ | ✅ |
| IIoT Features | ❌ | ❌ | ❌ | ✅ |

---

## 📦 CLOUD STORAGE STRUCTURE

```
gs://lehar-core-prod/
├── organizations/
│   ├── tata-motors/
│   │   ├── hr/
│   │   │   ├── employees.xlsx
│   │   │   └── attendance_2026-01.pdf
│   │   ├── production/
│   │   │   ├── reports/
│   │   │   └── machine_logs/
│   │   └── documents/
│   ├── abc-manufacturing/
│   └── xyz-textiles/
└── global/
    └── templates/
```

---

## 🔄 REQUEST/RESPONSE FLOW

### Protected Route Example:

```
1. Client Request
   GET /dashboard
   Headers: Authorization: Bearer <JWT_TOKEN>

2. Flask receives request
   │
   ├──> @token_required decorator intercepts
   │
   ├──> Extract token from header
   │
   ├──> Decode JWT token
   │       └──> Invalid/expired? → 401 Unauthorized
   │
   ├──> Load user from database
   │       └──> Not found/inactive? → 401 Unauthorized
   │
   ├──> Attach user to request context
   │
   └──> Execute route handler

3. Route Handler
   def dashboard(current_user):
       # Has access to authenticated user
       role = current_user.role.value
       org = current_user.organization
       
       # Render appropriate dashboard
       return render_template(f'{role}_dashboard.html')

4. Response
   200 OK
   Content: HTML dashboard page
```

---

## 🚀 DEPLOYMENT ARCHITECTURE

```
Developer commits code
    │
    ▼
GitHub/GitLab Repository
    │
    ▼
Cloud Build Trigger
    │
    ├──> Build Docker image
    │       └──> FROM python:3.11-slim
    │
    ├──> Run tests (optional)
    │
    ├──> Push to Container Registry
    │       └──> gcr.io/PROJECT_ID/lehar-core-app
    │
    └──> Deploy to Cloud Run
            ├──> Region: asia-south1
            ├──> Min instances: 0
            ├──> Max instances: 10
            ├──> Memory: 512Mi
            ├──> CPU: 1
            └──> Environment:
                ├──> Secrets from Secret Manager
                └──> Cloud SQL connection
```

---

## 📈 SCALING STRATEGY

### **Horizontal Scaling (Cloud Run)**
- Auto-scales from 0 to 10 instances
- Each instance handles ~80 concurrent requests
- Load balancer distributes traffic

### **Database Scaling (Cloud SQL)**
- Start with `db-f1-micro` (0.6 GB RAM)
- Upgrade to `db-n1-standard-1` for production
- Read replicas for heavy read workloads

### **Storage Scaling (Cloud Storage)**
- Unlimited storage capacity
- Regional buckets for low latency
- Lifecycle policies for cost optimization

---

## 🔒 SECURITY MEASURES

1. **Authentication**: JWT-based with secure token signing
2. **Password Hashing**: Werkzeug PBKDF2 with salt
3. **Email Verification**: Required for all new users
4. **Role-Based Access**: Enforced at route level
5. **Plan-Based Features**: Checked before module access
6. **Cloud SQL**: Private IP, SSL connections
7. **Secrets Management**: Google Secret Manager
8. **HTTPS Only**: Cloud Run enforces TLS

---

**Version**: 1.0  
**Last Updated**: January 30, 2026
