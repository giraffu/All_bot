from src.web_api.core.security import create_access_token
from datetime import timedelta

token = create_access_token(subject=8626302135, expires_delta=timedelta(minutes=60))
print(token)
