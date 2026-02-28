import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_data(user_id):
    return supabase.table("users").select("*").eq("user_id", user_id).single().execute()

def insert_notifications(data):
    if not data: return
    return supabase.table("notifications").insert(data).execute()