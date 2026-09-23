"""Read-only, account-bound YouTube Analytics for a confirmed local publication.

Official report/schema/metric sources checked 2026-09-20:
https://developers.google.com/youtube/analytics/channel_reports#basic-stats
https://developers.google.com/youtube/analytics/reference/reports/query
https://developers.google.com/youtube/analytics/metrics
https://developers.google.com/youtube/analytics/dimensions#time-periods
"""
import copy
import datetime as dt
import math
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import publishing
import service_connections as services


ENDPOINT = 'https://youtubeanalytics.googleapis.com/v2/reports'
TIMEZONE = 'America/Los_Angeles'
BASIC_METRICS = {
    'engagedViews': 'engaged_views',
    'views': 'views',
    'estimatedMinutesWatched': 'estimated_minutes_watched',
    'averageViewDuration': 'average_view_duration_seconds',
    'averageViewPercentage': 'average_view_percentage',
    'subscribersGained': 'subscribers_gained',
}
REVENUE_METRICS = {'estimatedRevenue': 'estimated_revenue_eur'}
COUNT_METRICS = {'engagedViews', 'views', 'subscribersGained'}
POST_BINDING = ('id', 'revision', 'state', 'platform', 'connection_id', 'account_id', 'remote_id')


def _today():
    return dt.datetime.now(ZoneInfo(TIMEZONE)).date()


def validate_request(data):
    """Only saved-publication IDs and a bounded calendar period are accepted."""
    if not isinstance(data, dict) or set(data) - {'publication_id', 'start_date', 'end_date', 'include_revenue'}:
        raise ValueError('Richiesta Analytics non valida: scegli un post e il periodo.')
    identity = data.get('publication_id')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{12}', identity):
        raise ValueError('Scegli una pubblicazione salvata nello studio.')
    include_revenue = data.get('include_revenue', False)
    if type(include_revenue) is not bool:
        raise ValueError('La lettura dei ricavi deve essere scelta esplicitamente.')
    dates = []
    for field in ('start_date', 'end_date'):
        value = data.get(field)
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Inserisci le date nel formato AAAA-MM-GG.')
        try:
            dates.append(dt.date.fromisoformat(value))
        except ValueError:
            raise ValueError('Una delle date del report non è valida.') from None
    start, end = dates
    if start > end or (end - start).days + 1 > 366:
        raise ValueError('Scegli un periodo ordinato da 1 a 366 giorni inclusi.')
    if end > _today():
        raise ValueError('Il report non può terminare dopo oggi nel fuso Pacifico di YouTube.')
    return {'publication_id': identity, 'start_date': start.isoformat(),
            'end_date': end.isoformat(), 'include_revenue': include_revenue}


def _number(value, metric):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or (metric != 'estimatedRevenue' and number < 0):
        return None
    if metric in COUNT_METRICS:
        return int(number) if number.is_integer() else None
    return number


def parse_report(payload, mapping):
    """A dimensionless report has at most one row; absent data never becomes zero."""
    values = {key: None for key in mapping.values()}
    if not isinstance(payload, dict):
        raise ValueError('Formato del report YouTube non riconosciuto.')
    headers = payload.get('columnHeaders', [])
    rows = payload.get('rows', [])
    if not isinstance(headers, list) or not isinstance(rows, list) or len(rows) > 1:
        raise ValueError('YouTube ha restituito una tabella diversa dal riepilogo richiesto.')
    positions = {}
    for index, header in enumerate(headers):
        if not isinstance(header, dict) or not isinstance(header.get('name'), str) or header['name'] in positions:
            raise ValueError('Intestazioni del report YouTube non valide.')
        if header.get('columnType') != 'METRIC':
            raise ValueError('Il report YouTube include una dimensione non richiesta.')
        positions[header['name']] = index
    if not rows:
        return values, 'no_data'
    row = rows[0]
    if not isinstance(row, list) or not headers or len(row) != len(headers):
        raise ValueError('Valori e intestazioni del report YouTube non corrispondono.')
    for metric, key in mapping.items():
        if metric in positions:
            values[key] = _number(row[positions[metric]], metric)
    return values, 'available' if all(value is not None for value in values.values()) else 'partial'


def _assert_binding(post, profile_id, revision):
    cfg = services.config('youtube', profile_id)
    if (cfg.get('id') != profile_id or cfg.get('revision', 0) != revision
            or cfg.get('account_id') != post['account_id'] or not cfg.get('verified')):
        raise ValueError('Il profilo YouTube è cambiato durante la lettura. Ricollega il canale del post e riprova.')
    with publishing.LOCK:
        current = publishing.find(publishing.load(), post['id'])
        if any(current.get(field) != post.get(field) for field in POST_BINDING):
            raise ValueError('La pubblicazione è cambiata durante la lettura. Ricarica il post e riprova.')


def _query(post, request, mapping, headers, monetary=False):
    params = {'ids': 'channel==MINE', 'startDate': request['start_date'],
              'endDate': request['end_date'], 'filters': 'video==' + post['remote_id'],
              'metrics': ','.join(mapping)}
    if monetary:
        params['currency'] = 'EUR'
    # Basic user activity statistics supports these metrics with no dimensions and
    # a video filter. Never accept endpoint/filters/metrics from user input.
    response, _, _ = services.http(ENDPOINT + '?' + urlencode(params), headers=headers)
    return response


def fetch_report(data):
    request = validate_request(data)
    with publishing.LOCK:
        post = copy.deepcopy(publishing.find(publishing.load(), request['publication_id']))
    if post.get('platform') != 'youtube' or post.get('state') != 'published':
        raise ValueError('Analytics richiede un video YouTube confermato come pubblicato nello studio.')
    for field in ('remote_id', 'account_id'):
        if not isinstance(post.get(field), str) or not re.fullmatch(r'[A-Za-z0-9_-]{2,180}', post[field]):
            raise ValueError('La pubblicazione non conserva un video e un canale YouTube validi.')
    profile_id = post.get('connection_id', 'default')
    cfg = services.profile_snapshot('youtube', profile_id)
    if not cfg.get('connected') or not cfg.get('verified'):
        raise ValueError('Collega e verifica il profilo YouTube del post prima di leggere Analytics.')
    if cfg.get('account_id') != post['account_id']:
        raise ValueError('Il canale collegato è diverso dal canale della pubblicazione.')
    revision = cfg.get('revision', 0)
    limitations = [
        'Il periodo richiesto usa giorni di calendario nel fuso Pacifico, non le prime 24 ore o i primi 7 giorni dal caricamento.',
        'I dati recenti possono essere incompleti: ogni query si ferma all’ultimo giorno disponibile per tutte le metriche richieste; la data effettiva non è esposta da questo riepilogo.',
        'La percentuale media vista non è una curva di retention né il tasso di completamento. Non sono letti impressioni, CTR o viewed-versus-swiped.',
        'Gli iscritti acquisiti con il filtro video si riferiscono alla pagina di visione di quel video, non a tutti gli iscritti del canale.',
    ]
    metrics = {key: None for key in (*BASIC_METRICS.values(), *REVENUE_METRICS.values())}
    monetary_status = 'not_requested'
    monetary_message = 'Ricavi non richiesti.'
    with services.bound('youtube', profile_id) as bound_profile:
        if bound_profile != profile_id:
            raise ValueError('Il profilo YouTube non corrisponde al post selezionato.')
        _assert_binding(post, profile_id, revision)
        who = services.verify('youtube', profile_id)
        if who.get('profile_id') != profile_id or who.get('account_id') != post['account_id']:
            raise ValueError('L’identità YouTube verificata è diversa da quella della pubblicazione.')
        _assert_binding(post, profile_id, revision)
        headers = services.auth('youtube', profile_id)
        _assert_binding(post, profile_id, revision)
        try:
            payload = _query(post, request, BASIC_METRICS, headers)
        except services.RemoteError:
            raise ValueError('Lettura YouTube Analytics non riuscita. Verifica rete, API abilitata e consenso yt-analytics.readonly; ricollega lo stesso canale con il permesso Analytics.') from None
        _assert_binding(post, profile_id, revision)
        basic, data_status = parse_report(payload, BASIC_METRICS)
        metrics.update(basic)
        if data_status == 'no_data':
            limitations.append('YouTube non ha restituito dati per questo intervallo. I valori restano non disponibili, non zero.')
        elif data_status == 'partial':
            limitations.append('Alcune metriche non sono state restituite o non sono valide: restano non disponibili.')
        if request['include_revenue']:
            _assert_binding(post, profile_id, revision)
            try:
                monetary_payload = _query(post, request, REVENUE_METRICS, headers, monetary=True)
            except services.RemoteError:
                monetary_status = 'unavailable'
                monetary_message = 'Ricavi non disponibili. Verifica il consenso yt-analytics-monetary.readonly, l’accesso del canale al Programma partner e la disponibilità del servizio.'
            else:
                try:
                    money, money_status = parse_report(monetary_payload, REVENUE_METRICS)
                except ValueError:
                    monetary_status = 'unavailable'
                    monetary_message = 'Il report dei ricavi non è interpretabile. Nessun importo è stato assunto.'
                else:
                    if money_status == 'available':
                        metrics.update(money)
                        monetary_status = 'available'
                        monetary_message = 'Ricavi netti stimati in EUR, soggetti a rettifiche; non equivalgono a un pagamento ricevuto.'
                    else:
                        monetary_status = 'no_data' if money_status == 'no_data' else 'unavailable'
                        monetary_message = 'YouTube non ha restituito una stima dei ricavi utilizzabile per il periodo. Il valore resta non disponibile.'
            _assert_binding(post, profile_id, revision)
            limitations.append('I ricavi sono una query separata, convertita in EUR dal servizio. Possono coprire meno giorni delle altre metriche; non viene calcolato un RPM combinando coperture sconosciute.')
        _assert_binding(post, profile_id, revision)
    return {'publication_id': post['id'], 'profile_id': profile_id, 'channel_id': post['account_id'],
            'period': {'start_date': request['start_date'], 'end_date': request['end_date'],
                       'timezone': TIMEZONE, 'note': 'Periodo richiesto inclusivo per giorni Pacifici; al cambio dell’ora un giorno dura 23 o 25 ore. Non è una finestra dalla pubblicazione.'},
            'metrics': metrics, 'data_status': data_status, 'monetary_status': monetary_status,
            'monetary_message': monetary_message, 'limitations': limitations,
            'source_url': 'https://www.youtube.com/watch?v=' + post['remote_id']}
