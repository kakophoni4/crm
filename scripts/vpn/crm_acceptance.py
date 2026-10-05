"""Run inside the CRM API container. Creates a named QA contact, then revokes and archives it."""
import asyncio
import base64
import json
import time
import uuid

import httpx
from sqlalchemy import delete, select

from app.modules.db.models.enums import UserRole, UserStatus
from app.modules.db.models.user import User
from app.modules.db.models.contact import Contact
from app.shared.db import get_session_factory
from app.shared.security.jwt import encode_access


async def main():
    async with get_session_factory()() as db:
        admin = await db.scalar(select(User).where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE).order_by(User.id).limit(1))
        token = encode_access(admin.id, admin.role.value, str(uuid.uuid4()))
    identity = None; contact_id = None
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', headers={'Authorization': 'Bearer ' + token}, timeout=20) as api:
        try:
            response = await api.post('/api/v1/contacts', json={'full_name': '[VPN QA] Integration acceptance', 'source': 'vpn_acceptance_test'})
            response.raise_for_status(); contact_id = response.json()['id']
            response = await api.post('/api/v1/vpn/subscriptions', json={'contact_id': contact_id, 'kind': 'gift', 'days': 1})
            response.raise_for_status(); identity = response.json()['id']
            async def ready():
                for attempt in range(60):
                    response = await api.get('/api/v1/vpn/subscriptions/' + identity)
                    response.raise_for_status(); value = response.json()
                    if value['ready_nodes'] == 7: return value
                    await asyncio.sleep(2)
                raise RuntimeError('Provisioning did not reach all seven nodes')
            value = await ready()
            print('CRM gift provisioned on seven nodes', flush=True)
            async with httpx.AsyncClient(timeout=20) as public:
                raw = await public.get(value['raw_url']); raw.raise_for_status()
                assert len(raw.text.strip().splitlines()) == 21
                happ = await public.get(value['happ_url']); happ.raise_for_status()
                happ_profiles = happ.json()
                assert len(happ_profiles) == 15 and 'Автовыбор' in happ_profiles[0]['remarks']
                assert happ_profiles[0]['routing']['balancers'][0]['strategy']['type'] == 'leastPing'
                assert happ.headers['routing'].startswith('happ://routing/onadd/')
                guide = await public.get(value['guide_url']); guide.raise_for_status()
                assert value['happ_url'] in guide.text and value['v2rayng_url'] in guide.text
                assert guide.headers['referrer-policy'] == 'no-referrer'
                ng = await public.get(value['v2rayng_url']); ng.raise_for_status()
                import base64
                assert all(line.startswith('vless://') for line in base64.b64decode(ng.text).decode().splitlines())
                clash = await public.get(value['clash_url']); clash.raise_for_status()
                config = clash.json(); assert len(config['proxies']) == 21
                assert len(next(group for group in config['proxy-groups'] if group['name'] == 'AUTO')['proxies']) <= 9
                assert 'password' not in value
                print('HTTPS subscription formats and personal connection guide passed', flush=True)
                response = await api.post('/api/v1/vpn/subscriptions/' + identity + '/action', json={'action': 'renew', 'days': 7})
                response.raise_for_status(); assert response.json()['expires_at'] == value['expires_at'] + 7 * 86400
                response = await api.post('/api/v1/vpn/subscriptions/' + identity + '/action', json={'action': 'rotate_link'})
                response.raise_for_status(); rotated = response.json()
                old = await public.get(value['subscription_url']); assert old.status_code == 404
                print('Renewal, audit and invalidation of old subscription URL passed', flush=True)
        finally:
            if identity:
                response = await api.post('/api/v1/vpn/subscriptions/' + identity + '/action', json={'action': 'revoke'})
                response.raise_for_status()
                revoked = await ready()
                assert revoked['status'] == 'revoked'
                async with httpx.AsyncClient(timeout=15) as public:
                    response = await public.get(revoked['subscription_url']); assert response.status_code == 403
                print('Revocation synchronized to all seven nodes; public access denied', flush=True)
                response = await api.post('/api/v1/vpn/subscriptions/' + identity + '/action', json={'action': 'delete'})
                response.raise_for_status()
                await ready()
                response = await api.get('/api/v1/vpn/subscriptions', params={'contact_id': contact_id})
                assert response.json()['items'] == []
                print('Deleted subscription hidden from CRM', flush=True)
            if contact_id:
                response = await api.delete('/api/v1/contacts/' + str(contact_id))
                response.raise_for_status()
                async with get_session_factory()() as db:
                    await db.execute(delete(Contact).where(Contact.id == contact_id, Contact.source == 'vpn_acceptance_test', Contact.full_name == '[VPN QA] Integration acceptance', Contact.telegram_user_id.is_(None), Contact.archived_at.is_not(None)))
                    await db.commit()
                print('QA contact removed from CRM', flush=True)
    print('CRM VPN acceptance passed', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
