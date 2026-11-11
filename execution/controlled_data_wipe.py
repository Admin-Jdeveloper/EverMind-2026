"""
execution/controlled_data_wipe.py

Controlled, auditable, safe data wipe tool for Evermind.
Guarantees:
1. Dry-run by default.
2. Identifies exact database host and environment.
3. Enumerates all target accounts and owned objects (items, chunks, facts, collections, tags, chats, S3 files).
4. Strictly requires explicit confirmation string before any destructive operation.
5. Deletes S3 files using application's delete_file storage service.
6. Uses atomic database transactions.
7. Outputs an audit summary to .tmp/data_wipe_audit_<timestamp>.json.
8. NEVER uses TRUNCATE or raw table drops.
"""

import os
import sys
import argparse
import datetime
import json
from pathlib import Path

# Setup Django environment
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "apps" / "api"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from content.models import Collection, Tag, ContentItem, ContentChunk, ContentFact, SavedSearch
from chat.models import ChatSession, ChatMessage, UserMemory
from content.storage import delete_file

User = get_user_model()


def get_audit_path():
    tmp_dir = repo_root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return tmp_dir / f"data_wipe_audit_{ts}.json"


def summarize_targets(users):
    """Summarize affected records across target users without exposing sensitive content."""
    user_ids = [u.id for u in users]
    
    items = ContentItem.objects.filter(user_id__in=user_ids)
    item_ids = list(items.values_list('id', flat=True))
    s3_files = list(items.exclude(file_key='').values_list('file_key', flat=True))
    
    chunks_count = ContentChunk.objects.filter(content_item_id__in=item_ids).count()
    facts_count = ContentFact.objects.filter(user_id__in=user_ids).count()
    collections_count = Collection.objects.filter(user_id__in=user_ids).count()
    tags_count = Tag.objects.filter(user_id__in=user_ids).count()
    searches_count = SavedSearch.objects.filter(user_id__in=user_ids).count()
    
    sessions = ChatSession.objects.filter(user_id__in=user_ids)
    session_ids = list(sessions.values_list('id', flat=True))
    messages_count = ChatMessage.objects.filter(session_id__in=session_ids).count()
    memories_count = UserMemory.objects.filter(user_id__in=user_ids).count()
    
    return {
        "user_count": len(users),
        "target_user_ids": [str(uid) for uid in user_ids],
        "content_items": len(item_ids),
        "s3_objects": len(s3_files),
        "s3_keys": s3_files,
        "content_chunks": chunks_count,
        "content_facts": facts_count,
        "collections": collections_count,
        "tags": tags_count,
        "saved_searches": searches_count,
        "chat_sessions": len(session_ids),
        "chat_messages": messages_count,
        "user_memories": memories_count,
    }


def execute_wipe(users, dry_run=True, confirm_token=None):
    db_settings = settings.DATABASES['default']
    db_host = db_settings.get('HOST', 'localhost')
    db_name = db_settings.get('NAME', 'unknown')
    
    print("\n" + "=" * 60)
    print("EVERMIND CONTROLLED DATA WIPE PROCEDURE")
    print("=" * 60)
    print(f"Environment:       {'PRODUCTION' if not settings.DEBUG else 'DEVELOPMENT'}")
    print(f"Database Host:     {db_host}")
    print(f"Database Name:     {db_name}")
    print(f"Storage Backend:   {getattr(settings, 'STORAGE_BACKEND', 's3')}")
    print(f"Dry Run Mode:      {dry_run}")
    print("=" * 60)
    
    if not users.exists():
        print("No target users found matching the scope.")
        return
    
    summary = summarize_targets(users)
    print("\n[AFFECTED RECORDS IN SCOPE]")
    print(f"  Target Users:          {summary['user_count']}")
    print(f"  Content Items:         {summary['content_items']}")
    print(f"  S3 Objects to Delete:  {summary['s3_objects']}")
    print(f"  Content Chunks (Embed):{summary['content_chunks']}")
    print(f"  Content Facts:         {summary['content_facts']}")
    print(f"  Collections:           {summary['collections']}")
    print(f"  Tags:                  {summary['tags']}")
    print(f"  Saved Searches:        {summary['saved_searches']}")
    print(f"  Chat Sessions:         {summary['chat_sessions']}")
    print(f"  Chat Messages:         {summary['chat_messages']}")
    print(f"  User Memories:         {summary['user_memories']}")
    print("=" * 60)
    
    if dry_run:
        print("\n>>> DRY RUN COMPLETE: No data was modified or deleted.")
        print("To execute this operation, run with --no-dry-run and provide --confirm-token.")
        return summary
    
    # Non-dry-run validation
    required_token = f"CONFIRM-WIPE-{summary['user_count']}-USERS"
    if confirm_token != required_token:
        print(f"\n[ERROR] Missing or invalid confirmation token!")
        print(f"Expected token: {required_token}")
        print("Aborting. No data was deleted.")
        sys.exit(1)
        
    print("\n[EXECUTION] Beginning transactional deletion...")
    audit_data = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "database_host": db_host,
        "database_name": db_name,
        "pre_wipe_summary": summary,
        "deleted_s3_files": [],
        "s3_errors": [],
        "success": False
    }
    
    # 1. Delete S3 files
    for key in summary["s3_keys"]:
        try:
            delete_file(key)
            audit_data["deleted_s3_files"].append(key)
        except Exception as e:
            audit_data["s3_errors"].append({"key": key, "error": str(e)})
            print(f"  [WARN] Failed to delete S3 key {key}: {e}")
            
    # 2. Database deletion within atomic transaction
    with transaction.atomic():
        user_ids = summary["target_user_ids"]
        
        # Purge items (chunks and facts cascade)
        ContentItem.objects.filter(user_id__in=user_ids).delete()
        # Purge collections
        Collection.objects.filter(user_id__in=user_ids).delete()
        # Purge tags
        Tag.objects.filter(user_id__in=user_ids).delete()
        # Purge saved searches
        SavedSearch.objects.filter(user_id__in=user_ids).delete()
        # Purge chat sessions (messages cascade)
        ChatSession.objects.filter(user_id__in=user_ids).delete()
        # Purge memories
        UserMemory.objects.filter(user_id__in=user_ids).delete()
        
    audit_data["success"] = True
    audit_file = get_audit_path()
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)
        
    print(f"\n[SUCCESS] Deletion completed successfully.")
    print(f"Audit log written to: {audit_file}")
    return audit_data


def main():
    parser = argparse.ArgumentParser(description="Controlled Evermind Data Wipe")
    parser.add_argument("--email", type=str, help="Specific user email to target")
    parser.add_argument("--all-users", action="store_true", help="Target all non-staff users")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate without deleting (default)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Actually execute deletions")
    parser.add_argument("--confirm-token", type=str, help="Confirmation token required for real wipe")
    args = parser.parse_args()
    
    if not args.email and not args.all_users:
        print("[ERROR] You must specify either --email <email> or --all-users.")
        sys.exit(1)
        
    if args.email:
        users = User.objects.filter(email=args.email)
    elif args.all_users:
        users = User.objects.filter(is_staff=False, is_superuser=False)
        
    execute_wipe(users, dry_run=args.dry_run, confirm_token=args.confirm_token)


if __name__ == "__main__":
    main()
