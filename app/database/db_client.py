from supabase import create_client, Client
from app.config import config

def get_supabase_client() -> Client:
    """Creates and returns a Supabase client instance."""
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be provided in config/env")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# Global client instance
supabase: Client = get_supabase_client()