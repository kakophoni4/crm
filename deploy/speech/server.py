"""Private, bounded CPU speech worker. Audio and results never leave this service."""
import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

app = FastAPI()
model = WhisperModel('/model', device='cpu', compute_type='int8', cpu_threads=2)
pool = ThreadPoolExecutor(max_workers=1)
jobs = {}
tasks = set()
MAX_BYTES = 20 * 1024 * 1024

def recognize(data):
    audio = decode_audio(io.BytesIO(data), sampling_rate=16000)
    if len(audio) > 16000 * 600:
        raise ValueError('too_long')
    segments, _ = model.transcribe(audio, beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return ' '.join(s.text.strip() for s in segments).strip()

async def run(key, data):
    try:
        result = await asyncio.get_running_loop().run_in_executor(pool, recognize, data)
        jobs[key] = {'status': 'ready', 'text': result[:100000], 'updated': time.monotonic()}
    except Exception:
        jobs[key] = {'status': 'failed', 'updated': time.monotonic()}

@app.get('/health')
def health():
    return {'ok': True}

@app.get('/jobs/{key}')
def status(key: str):
    return jobs.get(key, {'status': 'missing'})

@app.post('/jobs/{key}')
async def submit(key: str, request: Request):
    if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise HTTPException(400)
    now = time.monotonic()
    for old in list(jobs):
        if jobs[old]['status'] != 'processing' and now - jobs[old]['updated'] > 3600:
            del jobs[old]
    if key in jobs and jobs[key]['status'] != 'failed':
        return jobs[key]
    if sum(j['status'] == 'processing' for j in jobs.values()) >= 4:
        raise HTTPException(429, 'Busy')
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413)
    if not data:
        raise HTTPException(400)
    # Recheck after awaiting the body: simultaneous requests must not enqueue duplicates.
    if key in jobs and jobs[key]['status'] != 'failed':
        return jobs[key]
    if sum(j['status'] == 'processing' for j in jobs.values()) >= 4:
        raise HTTPException(429, 'Busy')
    jobs[key] = {'status': 'processing', 'updated': now}
    task = asyncio.create_task(run(key, bytes(data)))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return jobs[key]
