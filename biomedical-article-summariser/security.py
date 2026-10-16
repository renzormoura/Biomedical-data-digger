"""Defesas de rede para buscas feitas em nome do usuario.

O app busca paginas arbitrarias informadas pelo usuario (editoras, Google
Academico). Sem salvaguardas isso e um vetor de SSRF: o servidor poderia ser
induzido a acessar loopback, redes privadas ou endpoints de metadata da nuvem.

`safe_get` aplica, a cada salto de redirecionamento:
  * somente http/https;
  * rejeicao de hosts que resolvem para enderecos nao publicos;
  * limite de redirecionamentos;
  * limite de bytes lidos do corpo.

Limitacao conhecida: a validacao de DNS e a conexao sao etapas separadas, entao
um atacante com controle do DNS autoritativo poderia tentar "DNS rebinding".
Mitigar de forma completa exige fixar o IP na conexao (transport adapter), o que
foge do escopo; a protecao atual elimina o abuso trivial e os redirecionamentos
para redes internas.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Mapping
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 4
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class UnsafeURLError(ValueError):
    """A URL aponta para um destino que o servidor nao deve acessar."""


class ResponseTooLargeError(requests.RequestException):
    """O corpo da resposta excede o limite configurado."""


def _resolve_host(host: str) -> list[str]:
    """Resolve `host` para uma lista de IPs. Isolado para facilitar testes."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise UnsafeURLError(f"Nao foi possivel resolver o host '{host}'.") from error
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(address: str) -> bool:
    """True somente para enderecos roteaveis na internet publica."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_public_url(url: str) -> None:
    """Levanta `UnsafeURLError` se `url` nao for um destino publico seguro."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Esquema nao permitido: '{parsed.scheme or '(vazio)'}'.")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL sem host.")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs com credenciais embutidas nao sao permitidas.")
    addresses = [host] if _is_ip_literal(host) else _resolve_host(host)
    if not addresses:
        raise UnsafeURLError(f"Host sem enderecos: '{host}'.")
    blocked = [address for address in addresses if not is_public_ip(address)]
    if blocked:
        raise UnsafeURLError(f"O host '{host}' resolve para um endereco nao publico.")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _read_capped(response: requests.Response, max_bytes: int) -> bytes:
    declared = response.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise ResponseTooLargeError(f"Resposta de {declared} bytes excede o limite de {max_bytes}.")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError(f"Corpo da resposta excede o limite de {max_bytes} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)


def safe_get(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = 15,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> requests.Response:
    """GET que valida cada salto contra SSRF e limita o tamanho do corpo.

    O corpo ja vem lido (`response.content` e seguro de usar). Erros HTTP nao sao
    convertidos em excecao: o chamador decide com `raise_for_status()`.
    """
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        response = requests.get(
            current,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        location = response.headers.get("Location")
        if 300 <= response.status_code < 400 and location:
            response.close()
            current = urljoin(current, location)
            continue
        response._content = _read_capped(response, max_bytes)  # noqa: SLF001
        response._content_consumed = True  # type: ignore[attr-defined]  # noqa: SLF001
        return response
    raise requests.TooManyRedirects(f"Mais de {max_redirects} redirecionamentos para {url}.")
