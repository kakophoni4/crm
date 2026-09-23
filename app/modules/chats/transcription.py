import hashlib
import json
import httpx
from sqlalchemy import text
from app.shared.settings import get_settings
from app.shared.storage import get_file_storage

async def attachment_transcription(method, service, db, actor, chat_id, message_id, index):
    # Exactly the same scope/ownership checks as downloading the original audio.
    att = await service.get_attachment_info(actor, chat_id, message_id, index)
    if isinstance(att.get('transcript'), str):
        return {'status': 'ready', 'text': att['transcript']}
    name = str(att.get('filename') or att.get('name') or '').lower()
    if not (att.get('type') == 'voice' or str(att.get('mime') or '').startswith('audio/') or name.endswith(('.oga', '.ogg', '.opus', '.mp3', '.m4a', '.wav'))):
        return {'status': 'failed', 'error': 'Расшифровка доступна только для аудио'}
    key = hashlib.sha256(str(att['storage_key']).encode()).hexdigest()
    url = get_settings().speech_service_url.rstrip('/') + '/jobs/' + key
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            result = response.json()
            if method == 'POST' and result.get('status') in ('missing', 'failed'):
                data, _ = await get_file_storage().get_bytes(str(att['storage_key']))
                if len(data) > 20 * 1024 * 1024:
                    return {'status': 'failed', 'error': 'Максимальный размер аудио — 20 МБ'}
                response = await client.post(url, content=data, headers={'Content-Type': 'application/octet-stream'})
                if response.status_code == 429:
                    return {'status': 'failed', 'error': 'Распознавание занято. Повторите немного позже'}
                response.raise_for_status()
                result = response.json()
    except (httpx.HTTPError, ValueError):
        return {'status': 'failed', 'error': 'Локальное распознавание недоступно. Проверьте службу speech'}
    if result.get('status') == 'ready' and isinstance(result.get('text'), str):
        transcript = result['text'][:100000]
        # Update just this attachment field; never overwrite concurrent attachment changes.
        await db.execute(text("""UPDATE messages SET attachments = jsonb_set(attachments,
            CAST(:path AS text[]), CAST(:value AS jsonb))
            WHERE id=:mid AND chat_id=:cid
            AND attachments -> CAST(:idx AS integer) ->> 'storage_key' = :key"""),
            {'path': [str(index), 'transcript'], 'value': json.dumps(transcript),
             'mid': message_id, 'cid': chat_id, 'idx': index, 'key': att['storage_key']})
        await db.commit()
        return {'status': 'ready', 'text': transcript}
    if result.get('status') == 'processing':
        return {'status': 'processing'}
    return {'status': 'failed', 'error': 'Не удалось распознать. Допускается аудио до 10 минут; попробуйте снова'}
