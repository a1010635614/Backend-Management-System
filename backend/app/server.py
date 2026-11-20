"""Trust the private Compose edge subnet, including recreated gateway containers."""
import ipaddress
import os
from pathlib import Path
import sys


def trusted_proxies(route_file: str = '/proc/net/route') -> str:
    explicit = os.getenv('FORWARDED_ALLOW_IPS')
    if explicit:
        return explicit
    addresses = ['127.0.0.1', '::1']
    route = Path(route_file)
    rows = [line.split() for line in route.read_text().splitlines()[1:]] if route.exists() else []
    interfaces = {row[0] for row in rows if len(row) >= 8 and row[1] == '00000000' and int(row[3], 16) & 2}
    for row in rows:
        if len(row) >= 8 and row[0] in interfaces and row[1] != '00000000' and int(row[3], 16) & 1:
            address = ipaddress.IPv4Address(bytes.fromhex(row[1])[::-1])
            mask = ipaddress.IPv4Address(bytes.fromhex(row[7])[::-1])
            network = ipaddress.IPv4Network(f'{address}/{mask}', strict=False)
            if network.is_private and network.prefixlen >= 16:
                addresses.append(str(network))
    if len(addresses) == 2:
        raise RuntimeError('No private Compose edge subnet; set FORWARDED_ALLOW_IPS explicitly')
    return ','.join(dict.fromkeys(addresses))


if __name__ == '__main__':
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0',
                            '--port', '8000', '--workers', '1', '--proxy-headers',
                            '--forwarded-allow-ips', trusted_proxies()])
