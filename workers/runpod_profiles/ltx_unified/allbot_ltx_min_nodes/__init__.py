from __future__ import annotations

import gc
import math
import random
from typing import Any

try:
    import torch
except Exception:  # pragma: no cover - ComfyUI images are expected to include torch.
    torch = None  # type: ignore[assignment]


ANY_TYPE = "*"


class ImpactDummyInput:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {"required": {}}

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(self) -> tuple[None]:
        return (None,)


class TwoWaySwitch:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "selection_setting": (
                    "INT",
                    {"default": 1, "min": 1, "max": 2, "step": 1},
                ),
            },
            "optional": {
                "input_1": (ANY_TYPE,),
                "input_2": (ANY_TYPE,),
            },
        }

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(
        self,
        selection_setting: int = 1,
        input_1: Any = None,
        input_2: Any = None,
    ) -> tuple[Any]:
        return (input_1 if int(selection_setting) == 1 else input_2,)


class EasyInt:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "value": (
                    "INT",
                    {"default": 0, "min": -2147483648, "max": 2147483647, "step": 1},
                ),
            },
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("int",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(self, value: int = 0) -> tuple[int]:
        return (int(value),)


class MxSlider:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "Xi": (
                    "INT",
                    {"default": 0, "min": -2147483648, "max": 2147483647, "step": 1},
                ),
                "Xf": (
                    "FLOAT",
                    {"default": 0.0, "min": -2147483648.0, "max": 2147483647.0},
                ),
                "isfloatX": ("INT", {"default": 0, "min": 0, "max": 1, "step": 1}),
            },
        }

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("X",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(self, Xi: int = 0, Xf: float = 0.0, isfloatX: int = 0) -> tuple[int | float]:
        return (float(Xf) if int(isfloatX) else int(Xi),)


class RAMCleanup:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "clean_file_cache": ("BOOLEAN", {"default": True}),
                "clean_processes": ("BOOLEAN", {"default": True}),
                "clean_dlls": ("BOOLEAN", {"default": True}),
                "retry_times": ("INT", {"default": 3, "min": 0, "max": 20, "step": 1}),
            },
            "optional": {
                "anything": (ANY_TYPE,),
            },
        }

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(
        self,
        clean_file_cache: bool = True,
        clean_processes: bool = True,
        clean_dlls: bool = True,
        retry_times: int = 3,
        anything: Any = None,
    ) -> tuple[Any]:
        del clean_file_cache, clean_processes, clean_dlls, retry_times
        gc.collect()
        return (anything,)


class VRAMCleanup:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "offload_model": ("BOOLEAN", {"default": True}),
                "offload_cache": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "anything": (ANY_TYPE,),
            },
        }

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(
        self,
        offload_model: bool = True,
        offload_cache: bool = True,
        anything: Any = None,
    ) -> tuple[Any]:
        del offload_model, offload_cache
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        return (anything,)


class FloatLiteral:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "Number": ("STRING", {"default": "0.0"}),
            },
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("float",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(self, Number: str = "0.0") -> tuple[float]:
        return (float(Number),)


class IntToFloat:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "int_value": ("INT", {"default": 0}),
            },
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("float",)
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"

    def run(self, int_value: int = 0) -> tuple[float]:
        return (float(int_value),)


class AllBotLTXCropGuideLatentsExact:
    """Remove appended Ingredients guide latents using the requested output boundary."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "latent": ("LATENT",),
                "output_frames": (
                    "INT",
                    {"default": 121, "min": 1, "max": 10000, "step": 8},
                ),
            },
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("latent",)
    FUNCTION = "crop"
    CATEGORY = "AllBot/LTX/conditioning"

    def crop(self, latent: dict[str, Any], output_frames: int) -> tuple[dict[str, Any]]:
        target_latents = ((int(output_frames) - 1) // 8) + 1
        samples = latent.get("samples")
        if samples is None or len(samples.shape) != 5:
            raise ValueError("LTX latent samples must have shape B,C,T,H,W")
        if int(samples.shape[2]) < target_latents:
            raise ValueError(
                "LTX latent is shorter than the requested output boundary: "
                f"{samples.shape[2]} < {target_latents}"
            )

        cropped = dict(latent)
        cropped["samples"] = samples[:, :, :target_latents, :, :]
        noise_mask = latent.get("noise_mask")
        if noise_mask is not None:
            cropped["noise_mask"] = noise_mask[:, :, :target_latents, :, :]
        return (cropped,)


class SigmasSigmoid:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "sigmas": ("SIGMAS", {"forceInput": True}),
                "variant": (
                    ["logistic", "tanh", "softsign", "hardswish", "mish", "swish"],
                    {"default": "logistic"},
                ),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 10.0, "step": 0.01}),
                "offset": (
                    "FLOAT",
                    {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01},
                ),
                "normalize_output": ("BOOLEAN", {"default": True}),
            },
        }

    FUNCTION = "main"
    RETURN_TYPES = ("SIGMAS",)
    CATEGORY = "AllBot/LTX/min"

    def main(
        self,
        sigmas: Any,
        variant: str,
        gain: float,
        offset: float,
        normalize_output: bool,
    ) -> tuple[Any]:
        if torch is None:
            return (sigmas,)

        x = float(gain) * (sigmas + float(offset))
        if variant == "logistic":
            result = 1.0 / (1.0 + torch.exp(-x))
        elif variant == "tanh":
            result = torch.tanh(x)
        elif variant == "softsign":
            result = x / (1.0 + torch.abs(x))
        elif variant == "hardswish":
            result = x * torch.clamp(x + 3.0, min=0.0, max=6.0) / 6.0
        elif variant == "mish":
            result = x * torch.tanh(torch.log(1.0 + torch.exp(x)))
        elif variant == "swish":
            result = x * torch.sigmoid(x)
        else:
            result = x

        if normalize_output:
            result_min = result.min()
            result_max = result.max()
            denominator = result_max - result_min
            if torch.abs(denominator).item() > 0:
                result = (
                    (result - result_min)
                    / denominator
                    * (sigmas.max() - sigmas.min())
                    + sigmas.min()
                )

        return (result,)


class MathExpressionPysssss:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, Any]]:
        return {
            "required": {
                "expression": (
                    "STRING",
                    {"default": "0", "multiline": True, "dynamicPrompts": False},
                ),
            },
            "optional": {
                "a": (ANY_TYPE,),
                "b": (ANY_TYPE,),
                "c": (ANY_TYPE,),
            },
        }

    RETURN_TYPES = ("INT", "FLOAT")
    RETURN_NAMES = ("INT", "FLOAT")
    FUNCTION = "run"
    CATEGORY = "AllBot/LTX/min"
    OUTPUT_NODE = True

    def run(
        self,
        expression: str = "0",
        a: Any = None,
        b: Any = None,
        c: Any = None,
    ) -> tuple[int, float]:
        value = _safe_eval_math_expression(expression, a=a, b=b, c=c)
        return (int(value), float(value))


def _first_numeric(value: Any) -> float:
    if isinstance(value, (list, tuple)) and value:
        return _first_numeric(value[0])
    if isinstance(value, bool):
        return float(int(value))
    return float(value)


def _safe_eval_math_expression(expression: str, *, a: Any, b: Any, c: Any) -> float:
    allowed_globals = {
        "__builtins__": {},
        "abs": abs,
        "ceil": math.ceil,
        "floor": math.floor,
        "int": int,
        "max": max,
        "min": min,
        "round": round,
        "sqrt": math.sqrt,
        "randomint": lambda low, high: random.randint(int(low), int(high)),
        "randomchoice": lambda *items: random.choice(items),
        "iif": lambda value, truepart, falsepart: truepart if value else falsepart,
    }
    allowed_locals = {
        "a": _first_numeric(a) if a is not None else 0.0,
        "b": _first_numeric(b) if b is not None else 0.0,
        "c": _first_numeric(c) if c is not None else 0.0,
    }
    return float(eval(expression, allowed_globals, allowed_locals))


NODE_CLASS_MAPPINGS = {
    "ImpactDummyInput": ImpactDummyInput,
    "TwoWaySwitch": TwoWaySwitch,
    "easy int": EasyInt,
    "mxSlider": MxSlider,
    "RAMCleanup": RAMCleanup,
    "VRAMCleanup": VRAMCleanup,
    "Float": FloatLiteral,
    "IntToFloat": IntToFloat,
    "AllBotLTXCropGuideLatentsExact": AllBotLTXCropGuideLatentsExact,
    "Sigmas Sigmoid": SigmasSigmoid,
    "MathExpression|pysssss": MathExpressionPysssss,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    key: key
    for key in NODE_CLASS_MAPPINGS
}
