import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # Parse comma separated Admin IDs into list of integers
    ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS", "5570011875,6511741820")
    ADMIN_IDS: List[int] = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]
    
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "AserSupport")

config = Config()