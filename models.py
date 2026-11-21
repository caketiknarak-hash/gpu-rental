# -*- coding: utf-8 -*-
"""Canonical GPU model mapping (single source of truth).

Names were discovered from the real data on 2026-11-21:
  - GetDeploying slugs: weekly.csv unique gpu_slug
  - RunPod: gpuTypes[].id (the long id string, e.g. "NVIDIA A100-SXM4-80GB")
  - Vast.ai: offers[].gpu_name
"""

ATTRIBUTION = "GetDeploying, GPU rental price history, https://getdeploying.com/gpus, CC BY 4.0"

# runpod_primary: the id used for the headline secure/community price (SXM class where it exists)
# runpod_variants: other RunPod ids kept under runpod_variants (not merged into headline)
# vast_names: gpu_name values MERGED into one distribution for the model
# vast_min_vram_gb: drop Vast offers with less VRAM (used to keep A100 = 80GB class)
MODELS = {
    "b200": {
        "label": "NVIDIA B200", "vram_gb": 180, "launch": "2025-01", "launch_note": "approx; volume cloud availability 2025",
        "getdeploying": ["nvidia-b200"],
        "runpod_primary": "NVIDIA B200", "runpod_variants": [],
        "vast_names": ["B200"],
        "merge_note": "Single variant.",
    },
    "h200": {
        "label": "NVIDIA H200", "vram_gb": 141, "launch": "2024-03", "launch_note": "approx; cloud availability 2024",
        "getdeploying": ["nvidia-h200"],
        "runpod_primary": "NVIDIA H200", "runpod_variants": ["NVIDIA H200 NVL"],
        "vast_names": ["H200", "H200 NVL"],
        "merge_note": "GetDeploying: slug as published (variants not separable). RunPod headline = H200 SXM only (NVL kept in runpod_variants). Vast = H200 (SXM) + H200 NVL merged.",
    },
    "h100": {
        "label": "NVIDIA H100", "vram_gb": 80, "launch": "2023-03", "launch_note": "approx; announced 2022-09, cloud availability 2023",
        "getdeploying": ["nvidia-h100"],
        "runpod_primary": "NVIDIA H100 80GB HBM3", "runpod_variants": ["NVIDIA H100 PCIe", "NVIDIA H100 NVL"],
        "vast_names": ["H100 SXM", "H100 NVL", "H100 PCIE"],
        "merge_note": "GetDeploying: slug as published (variants not separable). RunPod headline = H100 SXM (PCIe/NVL in runpod_variants). Vast = SXM + NVL + PCIE merged (few SXM offers).",
    },
    "a100": {
        "label": "NVIDIA A100", "vram_gb": 80, "launch": "2020-05", "launch_note": "approx; announced 2020-05",
        "getdeploying": ["nvidia-a100"],
        "runpod_primary": "NVIDIA A100-SXM4-80GB", "runpod_variants": ["NVIDIA A100 80GB PCIe", "NVIDIA A100-SXM4-40GB"],
        "vast_names": ["A100 SXM4", "A100 PCIE"], "vast_min_vram_gb": 70,
        "merge_note": "GetDeploying has a single merged A100 slug (40GB/80GB, SXM/PCIe mixed) so a100_80 cannot be split there. RunPod headline = A100 SXM 80GB. Vast = SXM4 + PCIE, restricted to >=70GB VRAM (80GB class).",
    },
    "l40s": {
        "label": "NVIDIA L40S", "vram_gb": 48, "launch": "2023-08", "launch_note": "approx",
        "getdeploying": ["nvidia-l40s"],
        "runpod_primary": "NVIDIA L40S", "runpod_variants": [],
        "vast_names": ["L40S"],
        "merge_note": "Single variant.",
    },
    "rtx-5090": {
        "label": "GeForce RTX 5090", "vram_gb": 32, "launch": "2025-01", "launch_note": "approx; consumer card",
        "getdeploying": ["nvidia-rtx-5090"],
        "runpod_primary": "NVIDIA GeForce RTX 5090", "runpod_variants": [],
        "vast_names": ["RTX 5090"],
        "merge_note": "Single variant.",
    },
    "rtx-4090": {
        "label": "GeForce RTX 4090", "vram_gb": 24, "launch": "2022-10", "launch_note": "approx; consumer card",
        "getdeploying": ["nvidia-rtx-4090"],
        "runpod_primary": "NVIDIA GeForce RTX 4090", "runpod_variants": [],
        "vast_names": ["RTX 4090"],
        "merge_note": "Single variant.",
    },
    "mi300x": {
        "label": "AMD Instinct MI300X", "vram_gb": 192, "launch": "2023-12", "launch_note": "approx",
        "getdeploying": ["amd-mi300x"],
        "runpod_primary": "AMD Instinct MI300X OAM", "runpod_variants": [],
        "vast_names": [],
        "merge_note": "Not listed on Vast.ai (no offers found under any MI300X name).",
    },
}

STOCKS = ["NVDA", "CRWV", "NBIS", "ORCL"]
STOCK_START = "2024-07-01"
