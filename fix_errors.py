import glob
import re

files = glob.glob("src/core/task_core.py") + glob.glob("src/services/task_service.py")

for f in files:
    with open(f, "r") as file:
        content = file.read()
    
    new_content = content.replace(
        'if "Circuit is open" in error_msg or "CircuitBreakerOpenException" in str(type(e)):',
        'if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]) or "CircuitBreaker" in str(type(e)):'
    )
    
    with open(f, "w") as file:
        file.write(new_content)
