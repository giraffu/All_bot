import glob
import os

for path in glob.glob("workers/*/agent_main.py"):
    with open(path, "r") as f:
        content = f.read()

    if "asgi_correlation_id" in content:
        continue

    # Add imports
    content = content.replace("import sys\n", "import sys\nfrom asgi_correlation_id import correlation_id\n")

    # Update logger configuration to include correlation_id
    old_log_config = """logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)"""
    new_log_config = """class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        trace_id = correlation_id.get()
        record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"
        return True

log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(log_format))
handler.addFilter(CorrelationIdFilter())

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)"""
    content = content.replace(old_log_config, new_log_config)

    # Inject trace_id in process_task
    old_process_task = """    async def process_task(self, task: Dict[str, Any]):
        task_id = str(task.get("task_id", ""))"""
    new_process_task = """    async def process_task(self, task: Dict[str, Any]):
        trace_id = task.get("trace_id", "")
        if trace_id:
            correlation_id.set(trace_id)
            
        task_id = str(task.get("task_id", ""))"""
    content = content.replace(old_process_task, new_process_task)

    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path}")
