"""Địa chỉ IP của khách và danh sách mạng của quán (xác minh check-in qua wifi quán)."""
import ipaddress
from typing import Sequence

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _addr(text: str) -> IPAddress | None:
    try:
        value = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(value, ipaddress.IPv6Address) and value.ipv4_mapped:
        return value.ipv4_mapped
    return value


def _networks(items: Sequence[str]) -> list[Network]:
    result = []
    for item in items:
        try:
            result.append(ipaddress.ip_network(item.strip(), strict=False))
        except ValueError:
            continue
    return result


def ip_in_networks(ip: str, cidrs: Sequence[str]) -> bool:
    addr = _addr(ip)
    if addr is None:
        return False
    return any(addr.version == net.version and addr in net for net in _networks(cidrs))


def client_ip(peer: str | None, forwarded_for: str | None, trusted_proxies: Sequence[str]) -> str:
    """IP thật của client. Chỉ tin X-Forwarded-For khi kết nối đến từ proxy đã khai báo; khi đó lấy IP
    ngoài cùng bên phải không phải proxy tin cậy (phần bên trái do client tự khai nên không đáng tin)."""
    peer = peer or ""
    if not trusted_proxies or not forwarded_for or not ip_in_networks(peer, trusted_proxies):
        return peer
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        if _addr(hop) is None:
            return peer  # giá trị rác: không tin
        if not ip_in_networks(hop, trusted_proxies):
            return hop
    return peer


def normalize_cidr(text: str) -> str:
    """Chuẩn hoá IP/CIDR do chủ quán nhập. Từ chối dải quá rộng (không thể là mạng của một quán)."""
    try:
        network = ipaddress.ip_network(text.strip(), strict=False)
    except ValueError:
        raise ValueError("Địa chỉ IP/CIDR không hợp lệ.")
    if network.version == 4 and network.prefixlen < 16:
        raise ValueError("Dải IPv4 quá rộng (tối thiểu /16).")
    if network.version == 6 and network.prefixlen < 48:
        raise ValueError("Dải IPv6 quá rộng (tối thiểu /48).")
    return str(network)
