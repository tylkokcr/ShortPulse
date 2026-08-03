#!/usr/bin/env python3
"""Per-video cost model for running ShortPulse as a hosted, credit-based service.

Run:  python scripts/cost_model.py

Measured inputs come from real renders on this machine (Apple Silicon, MPS)
and are recorded in each project's timings.json. Priced inputs are quoted
from provider pricing pages — see SOURCES below. Everything else is an
assumption, and every assumption is named and adjustable at the top so you
can re-run this as real numbers come in.

The one thing this file will not do is pretend an estimate is a measurement.
"""

from dataclasses import dataclass

# --- SOURCES (checked 2026-08-01) -------------------------------------
# RunPod RTX 4090: $0.34/hr community, $0.69/hr secure
# RunPod L4: $0.39/hr | A40: $0.44/hr
# Replicate SDXL: $0.003 per image
# fal.ai SDXL: ~$0.006 per image
# Stripe standard: 2.9% + $0.30 per transaction

# --- MEASURED (backend/app/storage/projects/*/timings.json) ------------
# Apple Silicon / MPS, "short" preset, 5 scenes, RealVisXL @ 25 steps.
MEASURED = {
    "fast_hybrid": {"script": 14.03, "audio": 21.06, "visuals": 328.88, "ffmpeg": 26.54},
    "stock_media": {"script": 13.38, "audio": 19.93, "visuals": 11.46, "ffmpeg": 13.52},
}
SCENES_PER_VIDEO = 5

# --- ASSUMPTIONS (change these) ----------------------------------------
# How much faster a rented NVIDIA GPU is than this Mac's MPS backend.
# NOT measured — MPS is well off the pace for SDXL, but the exact ratio
# depends on the card. Shown as a range in the output because the answer
# is sensitive to it.
GPU_SPEEDUP_DIFFUSION = (3.0, 6.0)
# Non-diffusion stages (LLM, TTS, whisper, ffmpeg) are CPU/network bound
# and gain much less from a better GPU.
GPU_SPEEDUP_OTHER = 1.5

GPU_HOURLY_USD = 0.34  # RunPod RTX 4090, community cloud
IMAGE_API_USD_PER_IMAGE = 0.003  # Replicate SDXL
# Small CPU box for the non-visual stages when images come from an API.
CPU_HOURLY_USD = 0.02

STRIPE_PCT = 0.029
STRIPE_FIXED_USD = 0.30


@dataclass
class Line:
    label: str
    usd: float
    note: str = ""


def _sum(d: dict) -> float:
    return sum(d.values())


def rented_gpu(mode: str, speedup: float) -> float:
    """Cost of one video on an always-on rented GPU, counting only the
    seconds this video actually occupies the machine."""
    m = MEASURED[mode]
    visuals = m["visuals"] / speedup
    other = (m["script"] + m["audio"] + m["ffmpeg"]) / GPU_SPEEDUP_OTHER
    return (visuals + other) / 3600 * GPU_HOURLY_USD


def image_api() -> float:
    """Images from a per-image API; everything else on a cheap CPU box."""
    m = MEASURED["fast_hybrid"]
    cpu_seconds = (m["script"] + m["audio"] + m["ffmpeg"]) / GPU_SPEEDUP_OTHER
    return SCENES_PER_VIDEO * IMAGE_API_USD_PER_IMAGE + cpu_seconds / 3600 * CPU_HOURLY_USD


def stock_media_cpu() -> float:
    """No image generation at all — CPU-only work plus Pexels downloads."""
    return _sum(MEASURED["stock_media"]) / GPU_SPEEDUP_OTHER / 3600 * CPU_HOURLY_USD


def gpu_breakeven_videos_per_month() -> float:
    """An hourly GPU bills whether or not anyone is rendering. Below this
    monthly volume, per-image APIs are cheaper simply because you stop
    paying for idle time."""
    monthly_gpu = GPU_HOURLY_USD * 24 * 30
    return monthly_gpu / image_api()


def stripe_take(gross: float) -> float:
    return gross * STRIPE_PCT + STRIPE_FIXED_USD


def main() -> None:
    print("=" * 66)
    print("MEASURED (this Mac, MPS, 5 scenes, ~25s video)")
    print("=" * 66)
    for mode, m in MEASURED.items():
        total = _sum(m)
        share = m["visuals"] / total * 100
        print(f"{mode:12s} {total:6.1f}s total | visuals {m['visuals']:6.1f}s ({share:4.1f}% of it)")
    print()

    print("=" * 66)
    print("COMPUTE COST PER VIDEO")
    print("=" * 66)
    lo, hi = GPU_SPEEDUP_DIFFUSION
    for mode in ("fast_hybrid",):
        c_hi = rented_gpu(mode, lo)  # slower GPU -> higher cost
        c_lo = rented_gpu(mode, hi)
        print(
            f"rented GPU, {mode:12s} ${c_lo:.4f} – ${c_hi:.4f}   "
            f"(assumes {lo:.0f}-{hi:.0f}x faster than MPS)"
        )
    print(f"per-image API (Replicate)  ${image_api():.4f}   (5 x ${IMAGE_API_USD_PER_IMAGE}/image + CPU)")
    print(f"stock_media (no AI images) ${stock_media_cpu():.4f}   (CPU only)")
    print()

    print("=" * 66)
    print("THE THING THAT ACTUALLY DECIDES THE ARCHITECTURE")
    print("=" * 66)
    monthly = GPU_HOURLY_USD * 24 * 30
    be = gpu_breakeven_videos_per_month()
    print(f"An always-on ${GPU_HOURLY_USD}/hr GPU costs ${monthly:,.0f}/month whether or not it renders.")
    print(f"Break-even vs the per-image API: ~{be:,.0f} videos/month.")
    print("Below that, renting a GPU means paying mostly for idle time.")
    print()

    print("=" * 66)
    print("PAYMENT FEES BITE HARDEST ON SMALL TOP-UPS")
    print("=" * 66)
    for gross in (1, 5, 10, 25):
        fee = stripe_take(gross)
        print(
            f"  ${gross:>5.2f} purchase -> ${fee:.2f} fees "
            f"({fee / gross * 100:4.1f}%) -> ${gross - fee:.2f} net"
        )
    print()
    print("Stripe's fixed $0.30 makes tiny credit packs uneconomic; the fee")
    print("outweighs the compute by an order of magnitude at these volumes.")
    print()

    print("=" * 66)
    print("NOT IN THIS MODEL")
    print("=" * 66)
    for item in (
        "storage + CDN egress (each video is ~10MB)",
        "the ~7GB model download on every new GPU worker (cold start)",
        "failed renders you still paid compute for, and refunds/retries",
        "edge-tts has no commercial licence; Azure Speech is the paid path",
        "Pexels: attribution is required and not yet implemented in the code",
        "your time, which is the largest cost at this stage",
    ):
        print(f"  - {item}")


if __name__ == "__main__":
    main()
