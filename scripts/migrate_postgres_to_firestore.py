"""
PostgreSQL to Firestore Migration Script
Migrates data from Cloud SQL (PostgreSQL) to Cloud Firestore

Usage:
    python migrate_postgres_to_firestore.py

Environment Variables Required:
    - DATABASE_URL: PostgreSQL connection string
    - GCS_PROJECT_ID: Google Cloud Project ID
    - GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from google.cloud import firestore
from google.oauth2 import service_account

# Configuration
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/lehar_core_dev")
PROJECT_ID = os.getenv("GCS_PROJECT_ID")
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


def get_postgres_connection():
    """Create PostgreSQL connection"""
    engine = create_engine(POSTGRES_URL)
    return engine.connect()


def get_firestore_client():
    """Create Firestore client"""
    if CREDENTIALS_PATH and os.path.exists(CREDENTIALS_PATH):
        credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_PATH)
        return firestore.Client(project=PROJECT_ID, credentials=credentials)
    else:
        return firestore.Client(project=PROJECT_ID)


def convert_postgres_row_to_dict(row, columns):
    """Convert PostgreSQL row to dictionary"""
    return {col: row[i] for i, col in enumerate(columns)}


def migrate_organizations(pg_conn, fs_client):
    """Migrate organizations table"""
    print("Migrating organizations...")
    
    result = pg_conn.execute(text("SELECT * FROM organizations"))
    columns = result.keys()
    
    batch = fs_client.batch()
    count = 0
    
    for row in result:
        data = convert_postgres_row_to_dict(row, columns)
        org_id = data.pop('id')
        
        # Convert timestamps to datetime objects if they're strings
        for field in ['created_at', 'updated_at']:
            if field in data and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        
        doc_ref = fs_client.collection('organizations').document(org_id)
        batch.set(doc_ref, data)
        count += 1
        
        # Commit batch every 500 documents (Firestore limit)
        if count % 500 == 0:
            batch.commit()
            batch = fs_client.batch()
            print(f"  Migrated {count} organizations...")
    
    # Commit remaining
    if count % 500 != 0:
        batch.commit()
    
    print(f"✅ Migrated {count} organizations")
    return count


def migrate_users(pg_conn, fs_client):
    """Migrate users table"""
    print("Migrating users...")
    
    result = pg_conn.execute(text("SELECT * FROM users"))
    columns = result.keys()
    
    batch = fs_client.batch()
    count = 0
    
    for row in result:
        data = convert_postgres_row_to_dict(row, columns)
        user_id = data.pop('id')
        
        # Convert timestamps to datetime objects if they're strings
        for field in ['created_at', 'updated_at', 'last_login']:
            if field in data and data[field] and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        
        doc_ref = fs_client.collection('users').document(user_id)
        batch.set(doc_ref, data)
        count += 1
        
        # Commit batch every 500 documents
        if count % 500 == 0:
            batch.commit()
            batch = fs_client.batch()
            print(f"  Migrated {count} users...")
    
    # Commit remaining
    if count % 500 != 0:
        batch.commit()
    
    print(f"✅ Migrated {count} users")
    return count


def migrate_invitations(pg_conn, fs_client):
    """Migrate invitations table"""
    print("Migrating invitations...")
    
    result = pg_conn.execute(text("SELECT * FROM invitations"))
    columns = result.keys()
    
    batch = fs_client.batch()
    count = 0
    
    for row in result:
        data = convert_postgres_row_to_dict(row, columns)
        invitation_id = data.pop('id')
        
        # Convert timestamps to datetime objects if they're strings
        for field in ['created_at', 'expires_at', 'accepted_at']:
            if field in data and data[field] and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        
        doc_ref = fs_client.collection('invitations').document(invitation_id)
        batch.set(doc_ref, data)
        count += 1
        
        # Commit batch every 500 documents
        if count % 500 == 0:
            batch.commit()
            batch = fs_client.batch()
            print(f"  Migrated {count} invitations...")
    
    # Commit remaining
    if count % 500 != 0:
        batch.commit()
    
    print(f"✅ Migrated {count} invitations")
    return count


def verify_migration(pg_conn, fs_client):
    """Verify migration counts"""
    print("\n📊 Verifying migration...")
    
    # Count in PostgreSQL
    pg_orgs = pg_conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar()
    pg_users = pg_conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
    pg_invites = pg_conn.execute(text("SELECT COUNT(*) FROM invitations")).scalar()
    
    # Count in Firestore
    fs_orgs = len(list(fs_client.collection('organizations').stream()))
    fs_users = len(list(fs_client.collection('users').stream()))
    fs_invites = len(list(fs_client.collection('invitations').stream()))
    
    print("\nPostgreSQL → Firestore:")
    print(f"  Organizations: {pg_orgs} → {fs_orgs} {'✅' if pg_orgs == fs_orgs else '❌'}")
    print(f"  Users: {pg_users} → {fs_users} {'✅' if pg_users == fs_users else '❌'}")
    print(f"  Invitations: {pg_invites} → {fs_invites} {'✅' if pg_invites == fs_invites else '❌'}")
    
    if pg_orgs == fs_orgs and pg_users == fs_users and pg_invites == fs_invites:
        print("\n✅ Migration verification successful!")
        return True
    else:
        print("\n❌ Migration verification failed - counts don't match!")
        return False


def main():
    """Main migration function"""
    print("=" * 60)
    print("PostgreSQL → Firestore Migration")
    print("=" * 60)
    
    # Validate environment
    if not PROJECT_ID:
        print("❌ Error: GCS_PROJECT_ID environment variable not set")
        sys.exit(1)
    
    print(f"\nProject ID: {PROJECT_ID}")
    print(f"PostgreSQL: {POSTGRES_URL.split('@')[-1]}")  # Hide credentials
    
    # Confirm migration
    response = input("\n⚠️  This will migrate ALL data to Firestore. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        sys.exit(0)
    
    try:
        # Connect to databases
        print("\n🔌 Connecting to databases...")
        pg_conn = get_postgres_connection()
        fs_client = get_firestore_client()
        print("✅ Connected successfully")
        
        # Migrate data
        print("\n🚀 Starting migration...\n")
        start_time = datetime.now()
        
        org_count = migrate_organizations(pg_conn, fs_client)
        user_count = migrate_users(pg_conn, fs_client)
        invite_count = migrate_invitations(pg_conn, fs_client)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Verify migration
        success = verify_migration(pg_conn, fs_client)
        
        # Summary
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Duration: {duration:.2f} seconds")
        print(f"Organizations migrated: {org_count}")
        print(f"Users migrated: {user_count}")
        print(f"Invitations migrated: {invite_count}")
        print(f"Total documents: {org_count + user_count + invite_count}")
        print("=" * 60)
        
        if success:
            print("\n✅ Migration completed successfully!")
        else:
            print("\n⚠️  Migration completed with warnings - please review counts")
        
        # Close connections
        pg_conn.close()
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()