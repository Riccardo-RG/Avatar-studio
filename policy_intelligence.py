"""Local, dated editorial guidance. No network, publishing, or legal certification.

Only the bundled, reviewed catalog supplies rules. User scripts and source material
are data: they cannot replace dates, sources, or instructions in this module.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re

CATALOG_PATH = Path(__file__).with_name('policy_catalog.json')
STATUS_LABELS = {'active': 'Vigente alla data indicata', 'upcoming': 'Annunciata per il futuro',
                 'expired': 'Superata alla data indicata', 'unknown': 'Decorrenza non documentata'}
VERIFICATION_LABELS = {'fresh': 'Verificata di recente', 'stale': 'Verifica da rinnovare',
                       'not_yet_verified': 'Verifica successiva alla data richiesta'}
EU_COUNTRIES = frozenset('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE'.split())
COUNTRY_ALIASES = {'ITALIA': 'IT', 'ITALY': 'IT', 'SPAGNA': 'ES', 'SPAIN': 'ES',
                   'FRANCIA': 'FR', 'FRANCE': 'FR', 'GERMANIA': 'DE', 'GERMANY': 'DE',
                   'UK': 'GB', 'UNITED KINGDOM': 'GB', 'STATI UNITI': 'US', 'USA': 'US'}
ISO_COUNTRIES = frozenset('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split())
ENUMS = {'platform': {'youtube', 'tiktok', 'instagram', 'twitch', 'other'},
         'format': {'video', 'live'}, 'synthetic': {'realistic', 'cartoon', 'none'},
         'business_model': {'ads', 'affiliate', 'leads', 'services', 'community'},
         'source_kind': {'original', 'licensed', 'reused'}}


def _date(value=None):
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError('Data non valida: usare YYYY-MM-DD.')


def snapshot(as_of=None):
    """Return detached catalog rows with independent effective/verification states.

    effective_until is exclusive. Dates absent in official sources remain null;
    publication_date is recorded explicitly when used as the observation boundary.
    Verification becomes stale after 30 days; reading never refreshes checked_at.
    """
    current = _date(as_of)
    catalog = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    review_days = int(catalog['review_after_days'])
    sources = {}
    for rule in catalog['rules']:
        checked = _date(rule['checked_at'])
        due = checked + timedelta(days=review_days)
        start = _date(rule['effective_from']) if rule.get('effective_from') else None
        end = _date(rule['effective_until']) if rule.get('effective_until') else None
        if start and current < start:
            status = 'upcoming'
        elif end and current >= end:
            status = 'expired'
        elif start is None and current < checked:
            status = 'unknown'
        else:
            status = 'active'
        verification = 'not_yet_verified' if current < checked else ('stale' if current >= due else 'fresh')
        rule.update(status=status, status_label=STATUS_LABELS[status],
                    verification_status=verification, verification_label=VERIFICATION_LABELS[verification],
                    review_due_at=due.isoformat())
        source = sources.setdefault(rule['source_url'], {
            'url': rule['source_url'], 'source_url': rule['source_url'], 'title': rule['title'],
            'platform': rule['platform'], 'checked_at': rule['checked_at'],
            'review_due_at': due.isoformat(), 'verification_status': verification,
            'evidence_access': rule.get('evidence_access', 'official_page'), 'rule_ids': []})
        source['rule_ids'].append(rule['id'])
    return {'version': catalog['version'], 'checked_at': catalog['checked_at'], 'as_of': current.isoformat(),
            'review_after_days': review_days, 'rules': catalog['rules'], 'sources': list(sources.values()),
            'notes': ['Catalogo locale verificato manualmente: nessun monitoraggio automatico delle pagine.',
                      'Stato temporale e freschezza della verifica sono distinti: una regola vigente può richiedere una nuova verifica.',
                      'Le indicazioni non certificano conformità, monetizzazione, diritti o idoneità dell’account.']}


def assess(data, as_of=None):
    """Assess declared facts without submitting them anywhere or changing state.

    Optional details: is_short, shop, real_person, identity_consent,
    realistic_audio, ai_disclosed, commercial_disclosed, prerecording (booleans).
    Omitted facts are unknown, never inferred as authorizations. Results are
    advisory; review_required never prevents rendering or publishing by itself.
    """
    if not isinstance(data, dict):
        raise ValueError('Il controllo richiede un oggetto con i dati del contenuto.')
    catalog = snapshot(as_of)
    rules = {item['id']: item for item in catalog['rules']}
    findings = []
    values = {}

    def add(code, message, rule_id=None, severity='warning', **extra):
        rule = rules.get(rule_id, {})
        findings.append({'severity': severity, 'code': code, 'message': message,
                         'rule_id': rule_id, 'source_url': rule.get('source_url'),
                         'checked_at': rule.get('checked_at', catalog['checked_at']),
                         'effective_from': rule.get('effective_from'),
                         'status': rule.get('status', 'informational'),
                         'verification_status': rule.get('verification_status'), **extra})

    for key, allowed in ENUMS.items():
        raw = data.get(key)
        clean = raw.strip().lower() if isinstance(raw, str) else None
        values[key] = clean if clean in allowed else None
        if clean not in allowed:
            add('missing_' + key, 'Specificare un valore valido per ' + key + ': ' + ', '.join(sorted(allowed)) + '.')
    platform = values['platform']
    country_raw = data.get('country')
    country = country_raw.strip().upper() if isinstance(country_raw, str) else ''
    country = COUNTRY_ALIASES.get(country, country)
    if country not in ISO_COUNTRIES:
        country = None
        add('country_unknown', 'Paese dell’account non indicato: disponibilità dei programmi e requisiti locali restano da verificare.')
    duration = data.get('duration_seconds')
    try:
        duration = float(duration) if not isinstance(duration, bool) else float('nan')
    except (TypeError, ValueError, OverflowError):
        duration = float('nan')
    if not math.isfinite(duration) or duration <= 0:
        duration = None
        if values['format'] == 'video':
            add('duration_unknown', 'Indicare la durata effettiva del file esportato per verificare i limiti del formato.')
    for key in ('rights_confirmed', 'commercial', 'is_short', 'shop', 'real_person', 'identity_consent',
                'realistic_audio', 'ai_disclosed', 'commercial_disclosed', 'prerecording'):
        if key in data and not isinstance(data[key], bool):
            add('invalid_' + key, 'Il campo ' + key + ' deve essere sì/no; il valore ricevuto non vale come conferma.')
    commercial = data.get('commercial') is True or values['business_model'] in {'affiliate', 'leads', 'services'}
    synthetic = values['synthetic']
    realistic = synthetic == 'realistic' or data.get('realistic_audio') is True
    shop = data.get('shop') is True or data.get('publication_method') == 'shop'
    if data.get('rights_confirmed') is not True:
        add('rights_unconfirmed', 'Verificare l’utilizzo di immagini, video, musica, voce, personaggi e marchi; conservare le licenze pertinenti.', 'content_rights')
    if data.get('real_person') is True and data.get('identity_consent') is not True:
        add('identity_consent_missing', 'Per la persona reale indicata manca la conferma separata di autorizzazione su immagine e voce; i diritti sul file non bastano.', 'identity_permission')
    elif realistic and data.get('real_person') is not False:
        add('identity_scope_unknown', 'Se avatar o voce riproducono una persona reale, verificarne il consenso separatamente dai diritti sul materiale.', 'identity_permission', 'info')

    if platform == 'youtube':
        add('youtube_originality_review', rules['youtube_originality']['summary'], 'youtube_originality',
            'warning' if values['source_kind'] in {'licensed', 'reused'} else 'info')
        if values['business_model'] == 'ads':
            for rule_id in ('youtube_ypp_current', 'youtube_ypp_2027', 'youtube_shorts_pool_2027', 'youtube_terms_2027'):
                rule = rules[rule_id]
                if rule['status'] != 'expired':
                    add(rule_id, rule['summary'], rule_id, 'info', thresholds=rule.get('thresholds'))
        if realistic:
            add('youtube_ai_disclosure', 'Valutare e completare la dichiarazione AI realistica in Studio; il controllo locale non conferma che sia stata applicata.', 'youtube_ai_disclosure',
                'info' if data.get('ai_disclosed') is True else 'warning')
        elif synthetic == 'cartoon':
            add('youtube_cartoon_context', 'Il solo avatar cartoon non impone automaticamente la dichiarazione AI realistica; controllare separatamente voce, musica e scene.', 'youtube_ai_disclosure', 'info')
        # format=video alone is never taken as proof that the upload is a Short.
        if data.get('is_short') is True and values['format'] == 'video':
            if duration and duration > 180:
                add('youtube_short_too_long', 'La durata supera 180 secondi: preparare una versione entro il limite se la destinazione è Shorts.', 'youtube_shorts_length')
            else:
                add('youtube_short_classification', 'Verificare anche formato quadrato/verticale e classificazione effettiva in Studio.', 'youtube_shorts_length', 'info')
            if duration and 60 < duration < 180:
                add('youtube_claim_change', rules['youtube_claims_2026']['summary'] + ' I diritti vanno comunque verificati.', 'youtube_claims_2026', 'info')
            if values['business_model'] in {'affiliate', 'leads', 'services'}:
                add('youtube_short_conversion_path', rules['youtube_short_links']['summary'], 'youtube_short_links')
        if data.get('publication_method') in {'api', 'direct', 'direct_post'}:
            add('youtube_api_visibility', rules['youtube_api_public']['summary'], 'youtube_api_public', 'info')
        if commercial:
            add('youtube_commercial_disclosure', rules['youtube_branded']['summary'], 'youtube_branded',
                'info' if data.get('commercial_disclosed') is True else 'warning')
    elif platform == 'tiktok':
        if values['business_model'] == 'ads':
            add('tiktok_rewards_country_unverified', 'Creator Rewards non equivale a un pagamento per ogni visualizzazione: verificare paese, età, account personale e ammissione in TikTok Studio, anche se il paese è Italia.', 'tiktok_rewards')
            add('tiktok_rewards_requirements', rules['tiktok_rewards']['summary'], 'tiktok_rewards', 'info', thresholds=rules['tiktok_rewards']['thresholds'])
            if values['format'] == 'live':
                add('tiktok_rewards_live', 'Creator Rewards riguarda video idonei; per LIVE verificare programmi e requisiti separati.', 'tiktok_rewards')
            elif duration is not None and duration < 60:
                add('tiktok_rewards_too_short', 'Questo video dura meno di 60 secondi e non soddisfa il requisito di durata Creator Rewards.', 'tiktok_rewards')
            elif duration == 60:
                add('tiktok_rewards_boundary', 'Il file è esattamente al limite di un minuto: verificare durata rilevata e condizioni nel programma; una pagina ufficiale comparativa usa “oltre un minuto”.', 'tiktok_rewards_sponsored', 'info')
            if commercial:
                add('tiktok_rewards_commercial', 'Un contenuto sponsorizzato non è idoneo al Creator Rewards; distinguere quel programma dai ricavi della collaborazione.', 'tiktok_rewards_sponsored')
        if data.get('publication_method') in {'direct', 'direct_post', 'api'}:
            add('tiktok_direct_post_personal', rules['tiktok_direct_post']['summary'], 'tiktok_direct_post')
        elif data.get('publication_method') == 'inbox':
            add('tiktok_inbox_manual', 'L’upload Inbox prepara una bozza: completare la pubblicazione nell’app TikTok.', 'tiktok_direct_post', 'info')
        if realistic:
            add('tiktok_ai_disclosure', rules['tiktok_ai_disclosure']['summary'], 'tiktok_ai_disclosure',
                'info' if data.get('ai_disclosed') is True else 'warning')
        if commercial:
            add('tiktok_commercial_disclosure', rules['tiktok_commercial']['summary'], 'tiktok_commercial',
                'info' if data.get('commercial_disclosed') is True else 'warning')
        if shop or (commercial and values['format'] == 'live'):
            if not shop:
                add('tiktok_shop_scope', 'Se la diretta promuoverà prodotti su TikTok Shop, applicare anche le regole Shop del mercato interessato.', 'tiktok_shop_live', 'info')
            elif country not in rules['tiktok_shop_live']['countries']:
                add('tiktok_shop_region_unverified', 'Il catalogo descrive Shop UE nei mercati elencati dalla fonte; verificare le condizioni del mercato effettivo.', 'tiktok_shop_live')
            if shop and (country in rules['tiktok_shop_live']['countries'] or country is None) and values['format'] == 'live':
                add('tiktok_shop_live_realtime', rules['tiktok_shop_live']['summary'], 'tiktok_shop_live')
            if shop and (country in rules['tiktok_shop_ai']['countries'] or country is None) and synthetic in {'realistic', 'cartoon'}:
                add('tiktok_shop_ai_review', rules['tiktok_shop_ai']['summary'] + ' Verificare dichiarazione AI e fedeltà delle dimostrazioni.', 'tiktok_shop_ai')
    elif platform == 'instagram':
        if realistic:
            add('instagram_ai_disclosure', rules['instagram_ai']['summary'], 'instagram_ai',
                'info' if data.get('ai_disclosed') is True else 'warning')
        if commercial:
            add('instagram_commercial_disclosure', 'Se esiste una partnership con scambio di valore, usare l’etichetta dedicata; rendere comunque chiara la promozione.', 'instagram_branded',
                'info' if data.get('commercial_disclosed') is True else 'warning')
        if values['business_model'] == 'ads':
            add('instagram_revenue_program_unverified', rules['instagram_programs']['summary'] + ' Controllare le funzioni abilitate nel pannello professionale.', 'instagram_programs')
    elif platform:
        add('platform_not_covered', 'Il catalogo non copre in dettaglio questa piattaforma: consultare le relative condizioni prima della pubblicazione.')

    if commercial and (country in EU_COUNTRIES or country is None):
        add('eu_commercial_transparency', rules['eu_ads']['summary'], 'eu_ads', 'info')
    if (realistic or (values['format'] == 'live' and synthetic in {'realistic', 'cartoon'})) and (country in EU_COUNTRIES or country is None):
        add('eu_ai_scope_review', rules['eu_ai_transparency']['summary'] + ' Verificare l’ambito professionale e le eccezioni applicabili; il software non certifica conformità.', 'eu_ai_transparency', 'info')

    raw_script = data.get('script', '')
    if not isinstance(raw_script, str):
        add('script_invalid', 'Il copione deve essere testo; il controllo delle frasi non è stato eseguito.')
        script = ''
    else:
        script = raw_script[:50000].casefold()
        if len(raw_script) > 50000:
            add('script_truncated', 'Controllate le prime 50.000 lettere del copione; rivedere manualmente il resto.')
    if commercial and re.search(r'\b(guadagni garantiti|guadagno garantito|risultati garantiti|senza rischi|guaranteed (?:income|results|returns)|risk[ -]free|ganancias garantizadas|resultados garantizados|sin riesgos)\b', script):
        add('claims_review', 'Il testo contiene formule di garanzia assoluta: leggere contesto, eventuali negazioni e prove. È un segnale euristico, non un giudizio sulla veridicità.', 'eu_claims', heuristic=True)
    if commercial and synthetic in {'realistic', 'cartoon'} and re.search(r'\b(ho provato|ho usato|lo uso|l’ho usato|i (?:tried|used)|i use|he probado|he usado|lo uso yo)\b', script):
        add('experience_review', 'L’avatar usa una possibile testimonianza in prima persona: verificare a chi appartiene l’esperienza e non attribuirgli prove d’uso inventate. Il testo può anche citare un’esperienza reale.', 'eu_claims', heuristic=True)
    relevant = [rule for rule in catalog['rules'] if rule['platform'] in {platform, 'all'} and rule['status'] != 'expired']
    stale = [rule['id'] for rule in relevant if rule['verification_status'] == 'stale']
    if stale:
        add('policy_review_due', 'Sono trascorsi almeno 30 giorni dalla verifica delle fonti: ricontrollare le pagine ufficiali prima di basare decisioni su queste indicazioni.', rule_ids=stale)
    if any(rule['verification_status'] == 'not_yet_verified' for rule in relevant):
        add('historical_verification_unavailable', 'La data richiesta precede la ricerca: questo catalogo non ricostruisce con certezza tutte le regole storiche.')
    return {'platform': platform, 'country': country, 'checked_at': catalog['checked_at'],
            'as_of': catalog['as_of'], 'findings': findings, 'review_required': any(f['severity'] == 'warning' for f in findings),
            'notes': catalog['notes'] + ['Diritti, consenso sull’identità, idoneità alla monetizzazione e dichiarazioni AI/pubblicitarie sono verifiche separate.',
                                        'Nessun invio, etichetta o blocco automatico viene applicato da questo controllo. Le frasi segnalate richiedono lettura umana.']}
