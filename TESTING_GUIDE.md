# 🧪 LEHAR CORE - TESTING GUIDE

## ⚡ QUICK START (5 minutes)

### Step 1: Install Dependencies
```bash
cd /path/to/lehar-core-prod/backend

# Activate virtual environment (if not already)
source venv/bin/activate

# Install new dependencies (Flask-Login)
pip install -r requirements.txt
```

### Step 2: Start the Server
```bash
# Make sure you're in backend/ directory
python main.py
```

You should see:
```
 * Running on http://0.0.0.0:8080
 * Debug mode: on
```

### Step 3: Open Browser
```
http://localhost:8080
```

You should see the Lehar Core welcome page with Login and Sign Up buttons.

---

## 🎯 TESTING FLOW

### ✅ TEST 1: Homepage (/)

**URL**: `http://localhost:8080`

**Expected Result:**
- Welcome page loads
- "Lehar Core Platform" heading visible
- "Login" button present
- "Sign Up" button present

**Screenshot Expected:**
```
╔═══════════════════════════════════════╗
║  🏭 Lehar Core Platform              ║
║  Multi-tenant Industrial ERP System   ║
║                                       ║
║  ✅ System is Running Successfully!  ║
║                                       ║
║  [🔐 Login]  [📝 Sign Up]           ║
╚═══════════════════════════════════════╝
```

---

### ✅ TEST 2: Signup Page (/auth/signup)

**URL**: `http://localhost:8080/auth/signup`

**Expected Result:**
- Registration form loads
- Fields present:
  - Company Name *
  - Industry Type (dropdown)
  - Company Size (dropdown)
  - Website
  - Full Name *
  - Work Email *
  - Password *
  - Phone Number
  - Job Role

**Test Cases:**

#### Test 2a: Successful Signup
```
Fill in form:
✓ Company Name: "Test Manufacturing"
✓ Industry Type: "Manufacturing"
✓ Company Size: "50-200"
✓ Full Name: "John Doe"
✓ Email: "john@testmfg.com"
✓ Password: "SecurePass123"
✓ Phone: "+911234567890"

Click "Create Organization"

Expected:
✓ Redirect to login page
✓ Flash message: "Registration successful! Please check your email..."
✓ Database: organization created
✓ Database: user created with role='super_admin'
✓ Email sent (check logs if SMTP configured)
```

#### Test 2b: Validation Errors
```
Test weak password:
✗ Password: "weak"
Expected: Error message "Password must be at least 8 characters long"

Test invalid email:
✗ Email: "notanemail"
Expected: Error message "Invalid email address"

Test duplicate email:
✗ Email: "john@testmfg.com" (already used)
Expected: Error message about existing user
```

---

### ✅ TEST 3: Login Page (/auth/login)

**URL**: `http://localhost:8080/auth/login`

**Expected Result:**
- Login form loads
- Email field present
- Password field present
- "Login" button present

**Test Cases:**

#### Test 3a: Successful Login (WITHOUT Email Verification)
```
⚠️ NOTE: By default, email verification is required!

If you want to test login immediately after signup:
```

**OPTION 1: Disable Email Verification (for testing)**

Edit `backend/app/services/user_service.py`:
```python
# Find this line in authenticate():
if not user.is_email_verified:
    return None, "Please verify your email before logging in"

# Comment it out temporarily:
# if not user.is_email_verified:
#     return None, "Please verify your email before logging in"
```

**OPTION 2: Manually Verify in Database**
```bash
# Connect to database
psql -U lehar_user -d lehar_core_dev

# Verify the user
UPDATE users SET is_email_verified = true WHERE email = 'john@testmfg.com';
```

**Then test login:**
```
✓ Email: "john@testmfg.com"
✓ Password: "SecurePass123"
Click "Login"

Expected:
✓ Redirect to /dashboard
✓ Flash message: "Welcome back, John Doe!"
✓ Navigation bar appears with user name
✓ Dashboard loads with user details
```

#### Test 3b: Failed Login
```
Test wrong password:
✓ Email: "john@testmfg.com"
✗ Password: "WrongPass123"

Expected:
✗ Stay on login page
✗ Error message: "Invalid email or password"

Test non-existent email:
✗ Email: "notfound@example.com"
✗ Password: "anything"

Expected:
✗ Error message: "Invalid email or password"
```

---

### ✅ TEST 4: Dashboard (/dashboard)

**URL**: `http://localhost:8080/dashboard` (after login)

**Expected Result:**
- Dashboard loads
- User details displayed:
  - Name
  - Email
  - Role (badge)
  - Organization name
  - Plan type
  - Email verification status
- Quick action cards visible
- Navigation bar with logout button

**Test Navigation:**
```
Click "Profile" → Should go to /dashboard/profile
Click "Organization" (if admin) → Should go to /dashboard/organization
Click "Logout" → Should logout and redirect to login
```

---

### ✅ TEST 5: Logout

**Action**: Click logout button in navigation

**Expected:**
- Redirect to `/auth/login`
- Flash message: "You have been logged out successfully"
- Try accessing `/dashboard` → Should redirect to login
- Navigation bar disappears

---

## 🔍 MANUAL DATABASE VERIFICATION

### Check Organization Created
```bash
psql -U lehar_user -d lehar_core_dev

SELECT id, name, slug, plan_type, is_active FROM organizations;
```

Expected output:
```
 id  |        name          |       slug          | plan_type | is_active
-----+----------------------+---------------------+-----------+-----------
 ... | Test Manufacturing   | test-manufacturing  | free      | t
```

### Check User Created
```sql
SELECT id, name, email, role, is_email_verified, organization_id FROM users;
```

Expected output:
```
 id  |   name    |       email          |    role      | is_email_verified
-----+-----------+----------------------+--------------+-------------------
 ... | John Doe  | john@testmfg.com     | super_admin  | f
```

### Check Sessions
```sql
-- Flask-Login uses sessions, so no table for that
-- But you can check last_login updates
SELECT email, last_login FROM users;
```

---

## 🐛 COMMON ISSUES & SOLUTIONS

### Issue 1: "Template not found"
```
Error: jinja2.exceptions.TemplateNotFound: index.html
```

**Solution:**
```bash
# Check template exists
ls backend/app/templates/index.html

# Restart server
python main.py
```

### Issue 2: "ModuleNotFoundError: No module named 'flask_login'"
```
Solution:
pip install Flask-Login==0.6.3
```

### Issue 3: Pages load but no styling
```
Solution:
- Check Bootstrap CDN link in base.html
- Internet connection required for CDN
```

### Issue 4: "Please verify your email before logging in"
```
Solution (for testing):
# Option 1: Update database
UPDATE users SET is_email_verified = true;

# Option 2: Comment out verification check in user_service.py
```

### Issue 5: Database connection error
```
Error: psycopg2.OperationalError: could not connect to server
```

**Solution:**
```bash
# Check PostgreSQL running
sudo service postgresql status

# Start if not running
sudo service postgresql start

# Check .env file has correct DATABASE_URL
cat .env | grep DATABASE_URL
```

---

## 🧪 API TESTING (Alternative to Browser)

### Using cURL

#### Test Signup
```bash
curl -X POST http://localhost:8080/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "API Test Corp",
    "name": "Jane Smith",
    "email": "jane@apicorp.com",
    "password": "SecurePass123",
    "industry_type": "Manufacturing",
    "company_size": "1-50"
  }'
```

#### Test Login
```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jane@apicorp.com",
    "password": "SecurePass123"
  }' \
  -c cookies.txt
```

#### Test Protected Route
```bash
curl http://localhost:8080/dashboard \
  -b cookies.txt
```

---

## 📊 TESTING CHECKLIST

- [ ] Homepage loads at http://localhost:8080
- [ ] Signup page accessible
- [ ] Can register new organization
- [ ] Organization created in database
- [ ] Admin user created in database
- [ ] Login page accessible
- [ ] Can login with correct credentials
- [ ] Dashboard loads after login
- [ ] User details displayed correctly
- [ ] Navigation bar appears when logged in
- [ ] Logout works
- [ ] Protected routes redirect to login when not authenticated
- [ ] Flash messages appear correctly

---

## 🎯 NEXT TESTING STEPS

After basic flow works:

1. **Test Multiple Users**
   - Create second organization
   - Verify domain checking works

2. **Test User Invitations**
   - As admin, invite a new user
   - Accept invitation
   - Check new user can login

3. **Test Role Permissions**
   - Login as viewer
   - Try accessing admin routes
   - Should get "Insufficient permissions"

4. **Test Plan Limits**
   - Free plan has 3 user limit
   - Try adding 4th user
   - Should get error

---

## 📝 LOGGING & DEBUGGING

### Enable Debug Logging
```python
# In main.py or config.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### View Flask Logs
```bash
# Logs appear in terminal where you ran `python main.py`
```

### Check Database Logs
```bash
# Connect to database
psql -U lehar_user -d lehar_core_dev

# Check recent records
SELECT * FROM users ORDER BY created_at DESC LIMIT 5;
```

---

## ✅ FINAL VERIFICATION

Your system is working correctly if:

1. ✅ Can access homepage
2. ✅ Can register organization
3. ✅ Can login (after email verification or manual verification)
4. ✅ Dashboard loads with correct user data
5. ✅ Navigation works
6. ✅ Logout works
7. ✅ Protected routes require authentication

**Congratulations! Your authentication system is now fully functional! 🎉**
