import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
from sqlalchemy import select, desc
import os
import requests
import io

# Some files are only in telegram server but the bot didn't download them properly? No, it says downloaded to local_path.
# If they don't exist on host, it means they are inside the docker container because the path wasn't mounted!
# Wait, let's check docker compose.
