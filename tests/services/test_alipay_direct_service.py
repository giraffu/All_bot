import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from src.services.alipay_direct_service import (
    AlipayDirectConfig,
    AlipayDirectService,
    load_alipay_direct_config,
)
from src.services.rmb_payment_service import RMBOrderQueryStatus


def _cert(key, *, common_name: str, serial: int):
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AllBot"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )


def _service():
    app_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    alipay_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = AlipayDirectConfig(
        app_id="2021000000000001",
        seller_id="2088000000000001",
        gateway_url="https://openapi.alipay.test/gateway.do",
        app_private_key=app_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        app_cert=_cert(app_key, common_name="app", serial=101).public_bytes(
            serialization.Encoding.PEM
        ),
        alipay_public_cert=_cert(
            alipay_key, common_name="alipay", serial=202
        ).public_bytes(serialization.Encoding.PEM),
        alipay_root_cert=_cert(
            root_key, common_name="root", serial=303
        ).public_bytes(serialization.Encoding.PEM),
        notify_url="https://api.example/api/pay/notify/alipay",
        return_base_url="https://web.example",
    )
    return AlipayDirectService(config), app_key, alipay_key


def test_create_page_payment_url_is_rsa2_signed_and_contains_certificate_sns():
    service, _app_key, _alipay_key = _service()

    result = service.create_payment_url(
        out_trade_no="ORDER-1",
        subject="Plan",
        amount=Decimal("0.01"),
        product="page",
        return_url="https://web.example/billing?order_id=bo_1",
    )

    query = parse_qs(urlparse(result["data"]["payurl"]).query)
    assert query["method"] == ["alipay.trade.page.pay"]
    assert query["app_cert_sn"] == [service.app_cert_sn]
    assert query["alipay_root_cert_sn"] == [service.alipay_root_cert_sn]
    assert query["notify_url"] == ["https://api.example/api/pay/notify/alipay"]
    assert query["sign_type"] == ["RSA2"]

    signed = "&".join(
        f"{key}={query[key][0]}" for key in sorted(query) if key != "sign"
    )
    service.app_public_key.verify(
        base64.b64decode(query["sign"][0]),
        signed.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_callback_rejects_wrong_app_seller_and_certificate_serial():
    service, _app_key, alipay_key = _service()
    valid = {
        "app_id": service.config.app_id,
        "seller_id": service.config.seller_id,
        "out_trade_no": "ORDER-1",
        "trade_no": "TRADE-1",
        "total_amount": "0.01",
        "trade_status": "TRADE_SUCCESS",
        "auth_app_id": service.config.app_id,
        "alipay_cert_sn": service.alipay_public_cert_sn,
        "sign_type": "RSA2",
    }
    signed = "&".join(f"{key}={valid[key]}" for key in sorted(valid))
    valid["sign"] = base64.b64encode(
        alipay_key.sign(signed.encode(), padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    assert service.verify_callback(valid) is True

    for field, value in (
        ("app_id", "wrong"),
        ("seller_id", "wrong"),
        ("alipay_cert_sn", "wrong"),
    ):
        invalid = dict(valid)
        invalid[field] = value
        assert service.verify_callback(invalid) is False


def test_query_response_requires_matching_certificate_and_rsa2_signature():
    service, _app_key, alipay_key = _service()
    response = {
        "code": "10000",
        "out_trade_no": "ORDER-1",
        "seller_id": service.config.seller_id,
        "trade_status": "TRADE_SUCCESS",
        "trade_no": "TRADE-1",
        "total_amount": "0.01",
    }
    raw_response = json.dumps(response, separators=(",", ":"), ensure_ascii=False)
    signature = base64.b64encode(
        alipay_key.sign(
            raw_response.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode()
    payload = (
        '{"alipay_trade_query_response":'
        + raw_response
        + ',"sign":'
        + json.dumps(signature)
        + ',"alipay_cert_sn":'
        + json.dumps(service.alipay_public_cert_sn)
        + "}"
    )

    assert service._verify_response_signature(
        payload, "alipay_trade_query_response"
    ) == response
    invalid = payload.replace(service.alipay_public_cert_sn, "wrong")
    with pytest.raises(ValueError, match="certificate serial"):
        service._verify_response_signature(invalid, "alipay_trade_query_response")


@pytest.mark.asyncio
async def test_query_order_verifies_response_using_gateway_charset(monkeypatch):
    service, _app_key, alipay_key = _service()
    response = {
        "code": "40004",
        "msg": "Business Failed",
        "sub_code": "ACQ.TRADE_NOT_EXIST",
        "sub_msg": "交易不存在",
    }
    raw_response = json.dumps(response, separators=(",", ":"), ensure_ascii=False)
    signature = base64.b64encode(
        alipay_key.sign(
            raw_response.encode("gbk"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    ).decode()
    payload = (
        '{"alipay_trade_query_response":'
        + raw_response
        + ',"sign":'
        + json.dumps(signature)
        + ',"alipay_cert_sn":'
        + json.dumps(service.alipay_public_cert_sn)
        + "}"
    )

    class FakeResponse:
        status = 200
        charset = "gbk"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def text(self):
            return payload

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "src.services.alipay_direct_service.aiohttp.ClientSession",
        FakeSession,
    )

    result = await service.query_order(
        out_trade_no="ORDER-MISSING",
        expected_amount="0.01",
    )

    assert result.status is RMBOrderQueryStatus.NOT_PAID


def test_enabled_config_requires_every_secret(monkeypatch):
    monkeypatch.setenv("ALIPAY_DIRECT_ENABLED", "true")
    for key in (
        "ALIPAY_APP_ID",
        "ALIPAY_SELLER_ID",
        "ALIPAY_APP_PRIVATE_KEY_B64",
        "ALIPAY_APP_CERT_B64",
        "ALIPAY_PUBLIC_CERT_B64",
        "ALIPAY_ROOT_CERT_B64",
        "ALIPAY_NOTIFY_URL",
        "ALIPAY_RETURN_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="ALIPAY_DIRECT_ENABLED"):
        load_alipay_direct_config(required_if_enabled=True)
