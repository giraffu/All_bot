from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from .config import get_settings


class SmsProviderError(RuntimeError):
    pass


class SmsVerificationProvider(ABC):
    @abstractmethod
    async def send_code(self, phone_number: str, out_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def check_code(
        self, phone_number: str, verify_code: str, out_id: str
    ) -> bool:
        raise NotImplementedError


class DisabledSmsVerificationProvider(SmsVerificationProvider):
    async def send_code(self, phone_number: str, out_id: str) -> str:
        raise SmsProviderError("sms_provider_unavailable")

    async def check_code(
        self, phone_number: str, verify_code: str, out_id: str
    ) -> bool:
        raise SmsProviderError("sms_provider_unavailable")


class AliyunPnvsSmsVerificationProvider(SmsVerificationProvider):
    def __init__(self) -> None:
        settings = get_settings()
        from alibabacloud_dypnsapi20170525.client import (
            Client as Dypnsapi20170525Client,
        )
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
        )
        config.endpoint = "dypnsapi.aliyuncs.com"
        self.client = Dypnsapi20170525Client(config)
        self.settings = settings

    async def send_code(self, phone_number: str, out_id: str) -> str:
        from alibabacloud_dypnsapi20170525 import models as pnvs_models
        from alibabacloud_tea_util import models as util_models

        request = pnvs_models.SendSmsVerifyCodeRequest(
            country_code="86",
            phone_number=phone_number,
            sign_name=self.settings.aliyun_sms_sign_name,
            template_code=self.settings.aliyun_sms_template_code,
            template_param=json.dumps(
                {"code": "##code##", "min": "5"}, separators=(",", ":")
            ),
            out_id=out_id,
            scheme_name=self.settings.aliyun_sms_scheme_name,
            code_length=6,
            valid_time=self.settings.sms_challenge_seconds,
            duplicate_policy=1,
            interval=self.settings.sms_send_cooldown_seconds,
            code_type=1,
            return_verify_code=False,
        )
        try:
            response = await asyncio.to_thread(
                self.client.send_sms_verify_code_with_options,
                request,
                util_models.RuntimeOptions(),
            )
        except Exception as exc:
            raise SmsProviderError("sms_send_failed") from exc
        body = response.body
        if not body.success or body.code != "OK":
            raise SmsProviderError("sms_send_failed")
        model = body.model
        return str(
            getattr(model, "biz_id", None)
            or getattr(model, "request_id", None)
            or out_id
        )

    async def check_code(
        self, phone_number: str, verify_code: str, out_id: str
    ) -> bool:
        from alibabacloud_dypnsapi20170525 import models as pnvs_models
        from alibabacloud_tea_util import models as util_models

        request = pnvs_models.CheckSmsVerifyCodeRequest(
            country_code="86",
            phone_number=phone_number,
            verify_code=verify_code,
            out_id=out_id,
            scheme_name=self.settings.aliyun_sms_scheme_name,
            case_auth_policy=2,
        )
        try:
            response = await asyncio.to_thread(
                self.client.check_sms_verify_code_with_options,
                request,
                util_models.RuntimeOptions(),
            )
        except Exception as exc:
            raise SmsProviderError("sms_check_failed") from exc
        body = response.body
        return bool(
            body.success
            and body.code == "OK"
            and getattr(body.model, "verify_result", None) == "PASS"
        )


def normalize_mainland_phone(phone_number: str) -> str:
    digits = re.sub(r"[\s()-]", "", phone_number.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    if not re.fullmatch(r"1[3-9][0-9]{9}", digits):
        raise ValueError("invalid_phone_number")
    return digits


def phone_digest(phone_number: str) -> str:
    secret = get_settings().phone_hash_secret.encode()
    return hmac.new(secret, phone_number.encode(), hashlib.sha256).hexdigest()


def mask_phone(phone_number: str) -> str:
    return f"{phone_number[:3]}****{phone_number[-4:]}"


@lru_cache
def get_sms_provider() -> SmsVerificationProvider:
    if get_settings().sms_provider == "aliyun_pnvs":
        return AliyunPnvsSmsVerificationProvider()
    return DisabledSmsVerificationProvider()
