from app.server import trusted_proxies


def test_only_the_private_default_interface_is_trusted(tmp_path, monkeypatch):
    monkeypatch.delenv('FORWARDED_ALLOW_IPS', raising=False)
    path = tmp_path / 'route'
    path.write_text('Iface Destination Gateway Flags RefCnt Use Metric Mask\n'
                    'eth1 00000000 010012AC 0003 0 0 0 00000000\n'
                    'eth1 000012AC 00000000 0001 0 0 0 0000FFFF\n'
                    'eth0 000013AC 00000000 0001 0 0 0 0000FFFF\n')
    assert trusted_proxies(str(path)) == '127.0.0.1,::1,172.18.0.0/16'


def test_missing_route_requires_explicit_configuration(tmp_path, monkeypatch):
    import pytest
    monkeypatch.delenv('FORWARDED_ALLOW_IPS', raising=False)
    with pytest.raises(RuntimeError):
        trusted_proxies(str(tmp_path / 'missing'))


def test_operator_can_supply_a_fixed_trusted_proxy(monkeypatch):
    monkeypatch.setenv('FORWARDED_ALLOW_IPS', '127.0.0.1,10.2.3.4')
    assert trusted_proxies() == '127.0.0.1,10.2.3.4'
