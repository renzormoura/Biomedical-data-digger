"""Pix: gera o "copia e cola" (BR Code estatico do Banco Central) com valor e identificador, sem depender de nenhum provedor.

O codigo segue o padrao EMV/BR Code do Pix: campos `id(2) + tamanho(2) + valor`, terminados pelo CRC16-CCITT (polinomio 0x1021,
inicio 0xFFFF). E um QR **estatico com valor**: qualquer app de banco paga; a conciliacao e feita pelo administrador conferindo o
extrato (valor, data e, quando o banco mostra, o identificador). Quando houver provedor com API de cobranca (QR dinamico e
webhook), este modulo e substituido sem mudar o resto do fluxo.
"""

from __future__ import annotations

import re
import unicodedata


def crc16(payload: str) -> str:
    """CRC16-CCITT (False) em hexadecimal maiusculo, 4 caracteres."""
    crc = 0xFFFF
    for byte in payload.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _field(field_id: str, value: str) -> str:
    if len(value) > 99:
        raise ValueError(f"Campo {field_id} do Pix excede 99 caracteres.")
    return f"{field_id}{len(value):02d}{value}"


def _ascii(text: str, limit: int) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9 .\-]", "", plain).strip()[:limit]


def br_code(key: str, name: str, city: str, amount_cents: int, txid: str) -> str:
    """Pix "copia e cola" para pagar `amount_cents` a `key`, com o identificador `txid` (so letras e numeros, ate 25)."""
    key = key.strip()
    if not key:
        raise ValueError("Informe a chave Pix.")
    if amount_cents <= 0:
        raise ValueError("O valor deve ser positivo.")
    reference = re.sub(r"[^A-Za-z0-9]", "", txid)[:25] or "***"
    merchant = _field("00", "br.gov.bcb.pix") + _field("01", key)
    body = (
        _field("00", "01") + _field("01", "11")  # 11 = QR estatico reutilizavel
        + _field("26", merchant) + _field("52", "0000") + _field("53", "986")  # 986 = real
        + _field("54", f"{amount_cents // 100}.{amount_cents % 100:02d}") + _field("58", "BR")
        + _field("59", _ascii(name, 25) or "RECEBEDOR") + _field("60", _ascii(city, 15).upper() or "BRASIL")
        + _field("62", _field("05", reference))
    )
    body += "6304"
    return body + crc16(body)
