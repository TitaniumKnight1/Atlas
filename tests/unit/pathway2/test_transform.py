from __future__ import annotations

from backend.domain.pathway2.transform import DevTransformOptions, plan_dev_config_transform


def test_transform_writes_hostname_ports_and_udp_before_tcp() -> None:
    overlay = (
        "# overlay\n"
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        'sv_licenseKey "cfxk_dev_key"\n'
    )
    options = DevTransformOptions(hostname="[DEV] Team Server", max_clients=6, udp_port=30122, tcp_port=30122)
    proposed, meta = plan_dev_config_transform(overlay, options)
    assert '[DEV] Team Server' in proposed
    assert "sv_maxclients 6" in proposed
    assert 'endpoint_add_udp "0.0.0.0:30122"' in proposed
    assert 'endpoint_add_tcp "0.0.0.0:30122"' in proposed
    assert proposed.index("endpoint_add_udp") < proposed.index("endpoint_add_tcp")
    assert "sv_scriptHookAllowed" in proposed
    assert "set onesync on" in proposed
    assert meta["endpoints_order"] == "udp_before_tcp"
    assert 'sv_licenseKey "cfxk_dev_key"' in proposed


def test_transform_is_idempotent_on_reapply() -> None:
    overlay = 'sv_licenseKey "cfxk_dev_key"\n'
    first, _ = plan_dev_config_transform(overlay, DevTransformOptions())
    second, _ = plan_dev_config_transform(first, DevTransformOptions(hostname="[DEV] Updated"))
    assert second.count("# Atlas P2-3 dev transform") == 1
    assert "[DEV] Updated" in second
