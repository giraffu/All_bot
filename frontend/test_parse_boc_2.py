import base64
from pytoniq_core import Cell

def parse_payload_boc_hex(boc_hex: str) -> str:
    try:
        cell = Cell.one_from_boc(bytes.fromhex(boc_hex))
        slice = cell.begin_parse()
        opcode = slice.load_uint(32)
        if opcode == 0:
            return slice.load_snake_string()
        return None
    except Exception as e:
        return f"Error hex: {e}"

def parse_payload_boc_b64(boc_b64: str) -> str:
    try:
        cell = Cell.one_from_boc(base64.b64decode(boc_b64))
        slice = cell.begin_parse()
        opcode = slice.load_uint(32)
        if opcode == 0:
            return slice.load_snake_string()
        return None
    except Exception as e:
        return f"Error b64: {e}"

boc_str = "te6cckEBAQEAHwAAOgAAAABPUkRFUjoxMjM0NTY6MToxNzEwMDAwMDAwywtY4A=="
print("Hex parse result:", parse_payload_boc_hex(boc_str))
print("B64 parse result:", parse_payload_boc_b64(boc_str))
