FROM python:3.12-slim-bookworm
# NumPy 2.4+ wheels require x86-64-v2, which some VPS CPU profiles hide.
# Keep completed downloads between builds; retry interrupted package transfers.
RUN --mount=type=cache,target=/root/.cache/pip \
    for attempt in 1 2 3; do \
      python -m pip install --timeout 180 --retries 8 --progress-bar off \
        numpy==2.2.6 faster-whisper==1.2.1 fastapi==0.115.12 uvicorn==0.34.2 && exit 0; \
      if [ "$attempt" = 3 ]; then exit 1; fi; \
      sleep 5; \
    done
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/models')" && python -c "from huggingface_hub import snapshot_download; import shutil; shutil.copytree(snapshot_download('Systran/faster-whisper-small', cache_dir='/models'), '/model')" && rm -rf /models
COPY deploy/speech/server.py /app/server.py
ENV HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
USER 65534:65534
WORKDIR /app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
