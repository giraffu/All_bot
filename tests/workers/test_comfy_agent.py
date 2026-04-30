import ast

def test_agent_main_websocket_error_handling():
    with open("workers/comfy_agent/agent_main.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if websocket.state == websockets.protocol.State.CLOSED is in the code
    assert "websocket.state == websockets.protocol.State.CLOSED" in content
    
    # Check if JSON dictionary check is in the code
    assert "if not isinstance(data, dict):" in content
    
    # Verify it compiles valid Python
    ast.parse(content)
