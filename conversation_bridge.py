"""Reviewed Tavus data-channel commands; one controller, no automatic replay.

Only references and hashes are persisted. A browser dispatch is not a delivery
receipt and never means the avatar has actually pronounced the text.
"""
import hashlib
import json
import re
import time
import uuid
import broadcast
import providers

LEASES = {}
LEASE_SECONDS = 45
MAX_EVENTS = 200


def client(data):
    value = data.get('client_id', '')
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', value):
        raise ValueError('Identità della finestra non valida. Riapri la conversazione.')
    return value


def session(data):
    doc = broadcast.load()
    s = next((s for s in doc['sessions'] if s['id'] == data.get('id')), None)
    if not s or s['state'] != 'active' or s.get('deadline', 0) <= time.time():
        raise ValueError('La sessione Tavus non è attiva o ha raggiunto il limite di durata.')
    if not s.get('remote_id') or s['id'] not in broadcast.ROOMS:
        raise ValueError('Stanza non disponibile. Verifica la sessione sul servizio.')
    return doc, s


def owner(data):
    doc, s = session(data)
    lease = LEASES.get(s['id'], {})
    if lease.get('client_id') != client(data) or lease.get('expires', 0) <= time.time():
        raise ValueError('Controllo della stanza scaduto o aperto in un’altra finestra.')
    return doc, s


def expire_pending(s, controller=None):
    changed = False
    for event in s.get('bridge_events', []):
        if event['state'] == 'issued' and (controller is None or event['controller'] == controller):
            event.update(state='uncertain', updated=time.time())
            changed = True
    return changed


def claim(data):
    with broadcast.LOCK:
        doc, s = session(data)
        controller = client(data)
        previous = LEASES.get(s['id'], {})
        if previous.get('expires', 0) > time.time() and previous.get('client_id') != controller:
            raise ValueError('La conversazione è già controllata da un’altra finestra. Chiudila prima di continuare.')
        if previous.get('expires', 0) <= time.time() and expire_pending(s):
            providers.atomic_json(broadcast.PATH, doc)
        LEASES[s['id']] = {'client_id': controller, 'expires': time.time() + LEASE_SECONDS}
        return {**broadcast.room(s['id']), 'character_name': s.get('character_name', ''),
                'deadline': s['deadline'], 'lease_seconds': LEASE_SECONDS}


def heartbeat(data):
    with broadcast.LOCK:
        _, s = owner(data)
        LEASES[s['id']]['expires'] = time.time() + LEASE_SECONDS
        return {'ok': True, 'deadline': s['deadline']}


def release(data):
    with broadcast.LOCK:
        controller = client(data)
        identity = data.get('id')
        lease = LEASES.get(identity, {})
        if lease.get('client_id') == controller:
            LEASES.pop(identity, None)
            doc = broadcast.load()
            s = next((s for s in doc['sessions'] if s['id'] == identity), None)
            if s and expire_pending(s, controller):
                providers.atomic_json(broadcast.PATH, doc)
        return {'ok': True}


def issue(data, messages=()):
    if data.get('confirmed') is not True:
        raise ValueError('Rivedi il testo e conferma l’invio alla conversazione.')
    mode = data.get('mode', 'echo')
    if mode not in ('echo', 'respond', 'interrupt'):
        raise ValueError('Tipo di intervento non valido.')
    text = data.get('text', '')
    if not isinstance(text, str) or (mode != 'interrupt' and not 1 <= len(text.strip()) <= 600):
        raise ValueError('Inserisci un testo da 1 a 600 caratteri.')
    text = '' if mode == 'interrupt' else text.strip()
    source = data.get('source_message_id', '')
    if not isinstance(source, str):raise ValueError('Riferimento alla chat non valido.')
    if source and not any(m['id'] == source and m['state'] != 'dismissed' for m in messages):
        raise ValueError('Messaggio non più disponibile nella chat. Selezionane uno attuale.')
    digest = hashlib.sha256((mode + '\0' + text).encode()).hexdigest()
    with broadcast.LOCK:
        doc, s = owner(data)
        events = s.setdefault('bridge_events', [])
        if len(events) >= MAX_EVENTS:
            raise ValueError('Limite di interventi della sessione raggiunto.')
        if mode == 'interrupt':
            if any(e['mode'] == mode and time.time() - e['created'] < 1 for e in events):
                raise ValueError('Interruzione già richiesta. Attendi un istante.')
        elif any((source and e.get('source_message_id') == source) or e['digest'] == digest for e in events):
            raise ValueError('Intervento già inviato o con esito incerto: non verrà ripetuto.')
        payload = {'message_type': 'conversation', 'event_type': 'conversation.' + mode,
                   'conversation_id': s['remote_id']}
        if mode == 'echo':payload['properties'] = {'modality': 'text', 'text': text, 'done': True}
        elif mode == 'respond':payload['properties'] = {'text': text}
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 3800:
            raise ValueError('Testo troppo grande per il canale della conversazione.')
        event = {'id': uuid.uuid4().hex[:24], 'mode': mode, 'source_message_id': source,
                 'digest': digest, 'controller': client(data), 'state': 'issued', 'created': time.time()}
        events.append(event)
        # Persist before handing the command to the browser: a lost response is uncertain, never retried.
        providers.atomic_json(broadcast.PATH, doc)
        return {'event_id': event['id'], 'payload': payload}


def acknowledge(data):
    if data.get('state') not in ('dispatched', 'uncertain'):
        raise ValueError('Esito non valido.')
    with broadcast.LOCK:
        doc, s = owner(data)
        event = next((e for e in s.get('bridge_events', []) if e['id'] == data.get('event_id')), None)
        if not event or event['controller'] != client(data):raise ValueError('Intervento non trovato.')
        if event['state'] == 'issued':
            event.update(state=data['state'], updated=time.time())
            providers.atomic_json(broadcast.PATH, doc)
        return {'state': event['state']}


def recover():
    with broadcast.LOCK:
        LEASES.clear()
        doc = broadcast.load()
        changed = [expire_pending(s) for s in doc['sessions']]
        if any(changed):providers.atomic_json(broadcast.PATH, doc)
