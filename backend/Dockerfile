# ShortPulse API + render worker.
#
# No diffusion stack. It is ~3GB installed and needs a GPU to be worth
# running, so every torch/diffusers import in this codebase is inside the
# function that needs it and this image starts without them.
#
# That leaves stock_media, plus fast_hybrid when REPLICATE_API_TOKEN is
# set — the same checkpoint, generated over an API instead of on this
# machine. ai_video has no such route and is refused here: the API turns
# down a mode it cannot run rather than silently downgrading it, which is
# what it used to do. Add requirements-diffusion.txt and a GPU base image
# to run either of them locally.

FROM python:3.12-slim AS base

# ffmpeg is the renderer, not an optional extra. Debian's build includes
# libass, which the subtitle burn-in needs — the RUN below fails the build
# rather than letting a libass-less ffmpeg reach production, where the
# symptom is a video with no captions and no error.
#
# fonts-liberation gives fontconfig a baseline family so libass has
# something to fall back to; the caption font itself ships in
# app/assets/fonts and is passed to the filter explicitly.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-liberation \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version | grep -q -- --enable-libass \
    && ffprobe -version > /dev/null

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Piper voices and the Whisper model download on first use and are
    # several hundred MB. Pointing the cache at the data volume keeps them
    # across restarts — without this every cold start re-downloads them and
    # the first render of each deploy is minutes slower.
    HF_HOME=/data/models \
    XDG_DATA_HOME=/data/models

WORKDIR /app

# Dependencies before source, so editing code doesn't reinstall them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations

# Renders run as this user and write only under /data. Nothing in the
# pipeline needs root, and ffmpeg is fed URLs and files from outside.
RUN useradd --create-home --uid 10001 shortpulse \
    && mkdir -p /data/projects /data/models \
    && chown -R shortpulse:shortpulse /data /app
USER shortpulse

# Storage lives outside the image so it survives a redeploy. Projects are
# swept of their intermediates when a render finishes (see
# core/storage.discard_intermediates), but the finished videos stay.
ENV STORAGE_ROOT=/data/projects
VOLUME ["/data"]

EXPOSE 8000

# Single worker on purpose: renders are queued in-process and bounded by
# MAX_CONCURRENT_RENDERS. A second worker would double that limit without
# knowing it, and each holds its own copy of the Whisper model.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
