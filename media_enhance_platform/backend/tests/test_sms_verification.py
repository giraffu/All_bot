from types import SimpleNamespace

import pytest

from app.sms_verification import (
    AliyunPnvsSmsVerificationProvider,
    normalize_mainland_phone,
)


class FakePnvsClient:
    def __init__(self) -> None:
        self.sent_request = None
        self.checked_request = None

    def send_sms_verify_code_with_options(self, request, _runtime):
        self.sent_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                model=SimpleNamespace(biz_id="biz-123", request_id="req-123"),
            )
        )

    def check_sms_verify_code_with_options(self, request, _runtime):
        self.checked_request = request
        return SimpleNamespace(
            body=SimpleNamespace(
                success=True,
                code="OK",
                model=SimpleNamespace(verify_result="PASS"),
            )
        )


def provider_with_fake_client() -> tuple[AliyunPnvsSmsVerificationProvider, FakePnvsClient]:
    provider = object.__new__(AliyunPnvsSmsVerificationProvider)
    client = FakePnvsClient()
    provider.client = client
    provider.settings = SimpleNamespace(
        aliyun_sms_sign_name="system-sign",
        aliyun_sms_template_code="100005",
        aliyun_sms_scheme_name="clarity_phone",
        sms_challenge_seconds=300,
        sms_send_cooldown_seconds=60,
    )
    return provider, client


@pytest.mark.asyncio
async def test_aliyun_pnvs_adapter_uses_managed_code_send_and_check() -> None:
    provider, client = provider_with_fake_client()
    reference = await provider.send_code("13800138000", "challenge-1")
    assert reference == "biz-123"
    assert client.sent_request.phone_number == "13800138000"
    assert client.sent_request.sign_name == "system-sign"
    assert client.sent_request.template_code == "100005"
    assert client.sent_request.template_param == '{"code":"##code##","min":"5"}'
    assert client.sent_request.return_verify_code is False
    assert client.sent_request.valid_time == 300
    assert client.sent_request.interval == 60

    passed = await provider.check_code("13800138000", "246810", "challenge-1")
    assert passed is True
    assert client.checked_request.phone_number == "13800138000"
    assert client.checked_request.verify_code == "246810"
    assert client.checked_request.out_id == "challenge-1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("13800138000", "13800138000"),
        ("+86 138 0013 8000", "13800138000"),
        ("86-138-0013-8000", "13800138000"),
    ],
)
def test_mainland_phone_normalization(raw: str, expected: str) -> None:
    assert normalize_mainland_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12800138000", "1380013800", "+1 202 555 0100"])
def test_non_mainland_phone_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid_phone_number"):
        normalize_mainland_phone(raw)
