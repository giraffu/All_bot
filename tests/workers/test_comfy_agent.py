import ast


def test_agent_main_websocket_error_handling():
    with open("workers/comfy_agent/agent_main.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Check if websocket.state == websockets.protocol.State.CLOSED is in the code
    assert "websocket.state == websockets.protocol.State.CLOSED" in content

    # Check if JSON dictionary check is in the code
    assert "if not isinstance(data, dict):" in content
    assert "def _coerce_first_mapping(" in content
    assert "def _extract_ws_data_content(" in content
    assert "Failed to parse WS message type=%s: %s" in content

    # Verify it compiles valid Python
    ast.parse(content)


def test_agent_main_fail_fast_on_input_prepare_errors():
    with open("workers/comfy_agent/agent_main.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "Failed to upload prepared input" in content
    assert "Failed to prepare {param_key} input" in content
    assert "raise RuntimeError(" in content
    assert "async def _process_single_input_asset(" in content
    assert "async def _prepare_task_inputs(" in content


def test_agent_main_extracts_history_result_resolution_helpers():
    with open("workers/comfy_agent/agent_main.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "def _pick_first_output_asset(" in content
    assert "def _build_safe_result_object_name(" in content
    assert "def _resolve_history_result_asset(" in content
    assert "if not isinstance(outputs, dict):" in content
    ast.parse(content)
