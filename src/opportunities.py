"""Explicit opportunity commands; commercial stages never imply fake contacts."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any

from src.services import ZEPLIN_SERVICES

STAGES = ('new', 'contact', 'discovery', 'proposal', 'decision', 'won', 'lost')
SERVICE_SLUGS = {item['slug'] for item in ZEPLIN_SERVICES}
UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')


def integer(value, label, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > 2**53 - 1:
        raise ValueError(label + ' geçerli bir tam sayı olmalı.')
    return value


def command(payload: dict[str, Any]) -> dict[str, Any]:
    key = payload.get('idempotency_key')
    if not isinstance(key, str) or not UUID.fullmatch(key):
        raise ValueError('Geçerli işlem kimliği gerekli.')
    stage = payload.get('stage')
    if stage not in STAGES:
        raise ValueError('Geçerli fırsat aşaması seç.')
    note = payload.get('note', '')
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError('Geçiş notu en fazla 2000 karakter olmalı.')
    service = payload.get('service_slug')
    if service is not None and (not isinstance(service, str) or service not in SERVICE_SLUGS):
        raise ValueError('Hizmet katalogdan seçilmeli.')
    amount = payload.get('amount')
    amount_unknown = payload.get('amount_unknown')
    if not isinstance(amount_unknown, bool):
        raise ValueError('Tutarı veya “henüz bilinmiyor” seçeneğini belirt.')
    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
            raise ValueError('Tutar geçersiz.')
        try:
            number = Decimal(str(amount))
            if not number.is_finite() or number <= 0 or number > 1000000000 or number != number.quantize(Decimal('.01')):
                raise ValueError('Tutar 0 ile 1 milyar TL arasında, en fazla iki ondalık olmalı.')
            amount = format(number, '.2f')
        except InvalidOperation:
            raise ValueError('Tutar geçersiz.') from None
    if (amount is None) != amount_unknown:
        raise ValueError('Tutarı veya “henüz bilinmiyor” seçeneğini belirt.')
    if stage == 'lost' and not note.strip():
        raise ValueError('Kaybetme nedenini yaz.')
    values = {
        'lead_id': integer(payload.get('lead_id'), 'İşletme kimliği', minimum=1),
        'expected_lead': integer(payload.get('expected_lead_revision'), 'İşletme sürümü'),
        'expected_opportunity': integer(payload.get('expected_opportunity_revision'), 'Fırsat sürümü'),
        'stage': stage, 'note': note.strip(), 'amount': amount,
        'amount_unknown': amount_unknown, 'service': service,
    }
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'key': key, 'hash': hashlib.sha256(canonical.encode()).hexdigest(), **values}
