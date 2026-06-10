from __future__ import annotations


class RunPodProvider:
    """Future provider slot for RunPod Pods.

    The LAN controller v1 keeps this adapter intentionally inert so the planning
    layer can depend on a provider boundary without creating cloud resources.
    """

    provider = "runpod"

    def create_or_start(self, *_args, **_kwargs):
        raise NotImplementedError("RunPodProvider is a v2 provider stub")

    def stop_or_delete(self, *_args, **_kwargs):
        raise NotImplementedError("RunPodProvider is a v2 provider stub")
