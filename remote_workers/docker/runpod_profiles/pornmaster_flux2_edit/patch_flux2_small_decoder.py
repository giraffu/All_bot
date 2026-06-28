from __future__ import annotations

import os
from pathlib import Path


def _replace_once(path: Path, *, marker: str, old: str, new: str) -> str:
    text = path.read_text()
    if marker in text:
        return "already-patched"
    if old not in text:
        raise SystemExit(f"patch anchor not found in {path}")
    path.write_text(text.replace(old, new, 1))
    return "patched"


def main() -> None:
    comfyui_dir = Path(os.environ["COMFYUI_DIR"])
    autoencoder = comfyui_dir / "comfy" / "ldm" / "models" / "autoencoder.py"
    sd = comfyui_dir / "comfy" / "sd.py"

    auto_status = _replace_once(
        autoencoder,
        marker='decoder_ddconfig = kwargs.pop("decoder_ddconfig", ddconfig)',
        old="""        self.max_batch_size = kwargs.pop("max_batch_size", None)
        ddconfig = kwargs.pop("ddconfig")
        super().__init__(
            encoder_config={
                "target": "comfy.ldm.modules.diffusionmodules.model.Encoder",
                "params": ddconfig,
            },
            decoder_config={
                "target": "comfy.ldm.modules.diffusionmodules.model.Decoder",
                "params": ddconfig,
            },
            **kwargs,
        )
""",
        new="""        self.max_batch_size = kwargs.pop("max_batch_size", None)
        ddconfig = kwargs.pop("ddconfig")
        decoder_ddconfig = kwargs.pop("decoder_ddconfig", ddconfig)
        super().__init__(
            encoder_config={
                "target": "comfy.ldm.modules.diffusionmodules.model.Encoder",
                "params": ddconfig,
            },
            decoder_config={
                "target": "comfy.ldm.modules.diffusionmodules.model.Decoder",
                "params": decoder_ddconfig,
            },
            **kwargs,
        )
""",
    )

    sd_status = _replace_once(
        sd,
        marker="decoder_ch = sd['decoder.conv_in.weight'].shape[0] // ddconfig['ch_mult'][-1]",
        old="""                    if 'bn.running_mean' in sd:
                        ddconfig["batch_norm_latent"] = True
                        self.downscale_ratio *= 2
                        self.upscale_ratio *= 2
                        self.latent_channels *= 4
                        old_memory_used_decode = self.memory_used_decode
                        self.memory_used_decode = lambda shape, dtype: old_memory_used_decode(shape, dtype) *  4.0

                    if 'post_quant_conv.weight' in sd:
                        self.first_stage_model = AutoencoderKL(ddconfig=ddconfig, embed_dim=sd['post_quant_conv.weight'].shape[1])
                    else:
                        self.first_stage_model = AutoencodingEngine(regularizer_config={'target': "comfy.ldm.models.autoencoder.DiagonalGaussianRegularizer"},
                                                                    encoder_config={'target': "comfy.ldm.modules.diffusionmodules.model.Encoder", 'params': ddconfig},
                                                                    decoder_config={'target': "comfy.ldm.modules.diffusionmodules.model.Decoder", 'params': ddconfig})
""",
        new="""                    if 'bn.running_mean' in sd:
                        ddconfig["batch_norm_latent"] = True
                        self.downscale_ratio *= 2
                        self.upscale_ratio *= 2
                        self.latent_channels *= 4
                        old_memory_used_decode = self.memory_used_decode
                        self.memory_used_decode = lambda shape, dtype: old_memory_used_decode(shape, dtype) *  4.0

                    decoder_ch = sd['decoder.conv_in.weight'].shape[0] // ddconfig['ch_mult'][-1]
                    if decoder_ch != ddconfig['ch']:
                        decoder_ddconfig = ddconfig.copy()
                        decoder_ddconfig['ch'] = decoder_ch
                    else:
                        decoder_ddconfig = None

                    if 'post_quant_conv.weight' in sd:
                        self.first_stage_model = AutoencoderKL(ddconfig=ddconfig, embed_dim=sd['post_quant_conv.weight'].shape[1], **({"decoder_ddconfig": decoder_ddconfig} if decoder_ddconfig is not None else {}))
                    else:
                        self.first_stage_model = AutoencodingEngine(regularizer_config={'target': "comfy.ldm.models.autoencoder.DiagonalGaussianRegularizer"},
                                                                    encoder_config={'target': "comfy.ldm.modules.diffusionmodules.model.Encoder", 'params': ddconfig},
                                                                    decoder_config={'target': "comfy.ldm.modules.diffusionmodules.model.Decoder", 'params': decoder_ddconfig if decoder_ddconfig is not None else ddconfig})
""",
    )

    print(
        "flux2_small_decoder_patch "
        f"autoencoder={auto_status} sd={sd_status}"
    )


if __name__ == "__main__":
    main()
