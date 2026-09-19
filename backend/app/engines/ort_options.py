from __future__ import annotations

import onnxruntime as ort


def build_session_options(num_threads: int = 0) -> ort.SessionOptions:
    """Session options that keep CPU use bounded.

    Spinning is disabled so idle worker threads sleep instead of burning the
    container's CPU quota, and inter-op parallelism is pinned to one thread.

    The CPU memory arena and memory-pattern caching are also off. Tiles have varying
    shapes, and with the arena on ORT keeps growing (doubling) its pool: a 1020x1024 4x
    upscale peaked at ~7.5 GB, versus ~1.5 GB with these settings (at 256px tiles).
    """
    options = ort.SessionOptions()
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    if num_threads:
        options.intra_op_num_threads = num_threads
    return options
