import asyncio
from src.services.task_registry import TaskRegistry

async def main():
    tasks = await TaskRegistry.get_all_tasks()
    print("Total tasks:", len(tasks))
    for task_id, task_data in tasks.items():
        print(f"Task ID: {task_id}")
        print(f"  Username: {task_data.get('username')}")
        print(f"  Created At: {task_data.get('created_at', 'NOT FOUND')}")
        print("---")

asyncio.run(main())
