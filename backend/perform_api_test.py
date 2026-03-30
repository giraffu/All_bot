import os
import time
import requests
import json
from datetime import datetime

# Config
BASE_URL = "http://localhost:8003"
# Read .env for token
TOKEN = ""
ENV_PATH = "/home/ubantu/backend/.env"

if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            if line.startswith("AUTH_TOKEN="):
                TOKEN = line.split("=")[1].strip()
                break

if not TOKEN:
    print("Error: AUTH_TOKEN not found in .env")
    exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}
TEST_DATA_DIR = "/home/ubantu/backend/test_data"
OUTPUT_DIR = "/home/ubantu/backend/test_data"

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Read prompt
try:
    with open(os.path.join(TEST_DATA_DIR, "test_prompt.txt"), "r") as f:
        PROMPT = f.read().strip()
except FileNotFoundError:
    print("Error: test_prompt.txt not found")
    exit(1)

# Helper function
def submit_task(endpoint, files, data):
    url = f"{BASE_URL}{endpoint}"
    print(f"Submitting to {endpoint}...")
    try:
        resp = requests.post(url, headers=HEADERS, files=files, data=data)
        if resp.status_code == 200:
            task_id = resp.json()["task_id"]
            print(f"Task submitted: {task_id}")
            return task_id
        else:
            print(f"Error submitting task to {endpoint}: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"Exception submitting task to {endpoint}: {e}")
        return None

def wait_for_task(task_id, timeout=600): # 10 minutes timeout
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(f"{BASE_URL}/status/{task_id}", headers=HEADERS)
            if resp.status_code == 200:
                status = resp.json()
                state = status["status"]
                progress = status.get('progress', 0.0)
                # print(f"Task {task_id}: {state} (Progress: {progress:.2f})")
                
                if state == "done":
                    return status
                elif state == "error":
                    print(f"Task {task_id} failed: {status.get('error')}")
                    return status
            else:
                print(f"Error checking status: {resp.status_code}")
            
            time.sleep(5)
        except Exception as e:
            print(f"Exception checking status: {e}")
            time.sleep(5)
    return {"status": "timeout"}

def download_result(task_id, result_type, filename):
    endpoint = "/image" if result_type == "image" else "/video"
    url = f"{BASE_URL}{endpoint}/{task_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            path = os.path.join(OUTPUT_DIR, filename)
            with open(path, "wb") as f:
                f.write(resp.content)
            print(f"Result saved to {path}")
            return path
        else:
            print(f"Error downloading result: {resp.status_code}")
            return None
    except Exception as e:
        print(f"Exception downloading result: {e}")
        return None

def main():
    report = []
    tasks = []

    # 1. Img2Img
    img_path = os.path.join(TEST_DATA_DIR, "pic1.jpeg")
    if not os.path.exists(img_path):
        print(f"Error: {img_path} not found")
        return

    print("\n--- Starting Img2Img Test ---")
    files = {"image": open(img_path, "rb")}
    data = {"prompt": PROMPT, "priority": 1}
    task_id = submit_task("/comfy_img2img", files, data)
    if task_id:
        tasks.append({"type": "Img2Img", "id": task_id, "result_type": "image"})

    # 2. Face Swap
    img2_path = os.path.join(TEST_DATA_DIR, "pic2.jpeg")
    if not os.path.exists(img2_path):
        print(f"Error: {img2_path} not found")
        return

    print("\n--- Starting Face Swap Test ---")
    files = {
        "face_image": open(img_path, "rb"), # Face from pic1
        "body_image": open(img2_path, "rb")  # Body from pic2
    }
    data = {"priority": 1}
    task_id = submit_task("/face_swap", files, data)
    if task_id:
        tasks.append({"type": "Face Swap", "id": task_id, "result_type": "image"})

    # 3. Video Insert
    print("\n--- Starting Video Insert Test ---")
    files = {"image": open(img_path, "rb")}
    data = {"prompt": PROMPT, "priority": 1, "width": 512, "height": 512, "length": 24} 
    task_id = submit_task("/perfect_video_insert", files, data)
    if task_id:
        tasks.append({"type": "Video Insert", "id": task_id, "result_type": "video"})

    # 4. Video Edit
    print("\n--- Starting Video Edit Test ---")
    files = {"image": open(img_path, "rb")}
    data = {"prompt": PROMPT, "priority": 1, "width": 512, "height": 512, "length": 24}
    task_id = submit_task("/perfect_video_edit", files, data)
    if task_id:
        tasks.append({"type": "Video Edit", "id": task_id, "result_type": "video"})

    # Wait and collect results
    print("\nWaiting for tasks to complete...")
    final_report = "# 后端接口功能测试报告\n\n"
    final_report += f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    final_report += f"**测试提示词**: {PROMPT}\n\n"
    final_report += "| 功能 | 任务ID | 状态 | 耗时(秒) | 结果文件 |\n"
    final_report += "|---|---|---|---|---|\n"

    for task in tasks:
        print(f"Waiting for {task['type']} (ID: {task['id']})...")
        start_time = time.time()
        status = wait_for_task(task["id"])
        duration = time.time() - start_time
        
        result_file = "N/A"
        state = status.get("status", "unknown")
        
        if state == "done":
            ext = "png" if task["result_type"] == "image" else "mp4"
            filename = f"result_{task['type'].replace(' ', '_').lower()}_{task['id']}.{ext}"
            saved_path = download_result(task["id"], task["result_type"], filename)
            if saved_path:
                result_file = f"[{filename}]({filename})"
        
        final_report += f"| {task['type']} | {task['id']} | {state} | {duration:.1f} | {result_file} |\n"

    # Save report
    report_path = os.path.join(OUTPUT_DIR, "test_report_generated.md")
    with open(report_path, "w") as f:
        f.write(final_report)
    
    print("\n" + final_report)
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    main()
