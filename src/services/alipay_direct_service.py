from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from urllib.parse import urlencode, urlparse

import aiohttp
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.services.rmb_payment_service import (
    RMBOrderQueryResult,
    RMBOrderQueryStatus,
)

logger = logging.getLogger("alipay_direct")
AMOUNT_QUANT = Decimal("0.01")
DEFAULT_GATEWAY_URL = "https://openapi.alipay.com/gateway.do"
RSA_SIGNATURE_OID_PREFIX = "1.2.840.113549.1.1"


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_alipay_direct_enabled() -> bool:
    return _enabled(os.getenv("ALIPAY_DIRECT_ENABLED"))


def _decode_b64_env(name: str) -> bytes:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RuntimeError(f"{name} is not valid Base64") from exc


@dataclass(frozen=True)
class AlipayDirectConfig:
    app_id: str
    seller_id: str
    gateway_url: str
    app_private_key: bytes
    app_cert: bytes
    alipay_public_cert: bytes
    alipay_root_cert: bytes
    notify_url: str
    return_base_url: str


def load_alipay_direct_config(
    *, required_if_enabled: bool = True
) -> AlipayDirectConfig | None:
    if not is_alipay_direct_enabled() and required_if_enabled:
        return None
    required_names = (
        "ALIPAY_APP_ID",
        "ALIPAY_SELLER_ID",
        "ALIPAY_APP_PRIVATE_KEY_B64",
        "ALIPAY_APP_CERT_B64",
        "ALIPAY_PUBLIC_CERT_B64",
        "ALIPAY_ROOT_CERT_B64",
        "ALIPAY_NOTIFY_URL",
        "ALIPAY_RETURN_BASE_URL",
    )
    missing = [name for name in required_names if not os.getenv(name)]
    if missing:
        if is_alipay_direct_enabled():
            raise RuntimeError(
                "ALIPAY_DIRECT_ENABLED requires complete Alipay configuration: "
                + ", ".join(missing)
            )
        return None
    gateway_url = os.getenv("ALIPAY_GATEWAY_URL", DEFAULT_GATEWAY_URL)
    parsed_gateway = urlparse(gateway_url)
    if parsed_gateway.scheme != "https" or not parsed_gateway.hostname:
        raise RuntimeError("ALIPAY_GATEWAY_URL must be an HTTPS URL")
    return AlipayDirectConfig(
        app_id=str(os.environ["ALIPAY_APP_ID"]),
        seller_id=str(os.environ["ALIPAY_SELLER_ID"]),
        gateway_url=gateway_url,
        app_private_key=_decode_b64_env("ALIPAY_APP_PRIVATE_KEY_B64"),
        app_cert=_decode_b64_env("ALIPAY_APP_CERT_B64"),
        alipay_public_cert=_decode_b64_env("ALIPAY_PUBLIC_CERT_B64"),
        alipay_root_cert=_decode_b64_env("ALIPAY_ROOT_CERT_B64"),
        notify_url=str(os.environ["ALIPAY_NOTIFY_URL"]),
        return_base_url=str(os.environ["ALIPAY_RETURN_BASE_URL"]).rstrip("/"),
    )


def _load_private_key(data: bytes):
    candidates = [data]
    stripped = data.strip()
    if b"BEGIN" not in stripped:
        try:
            candidates.append(base64.b64decode(stripped, validate=True))
        except Exception:
            pass
    for candidate in candidates:
        try:
            if b"BEGIN" in candidate:
                return serialization.load_pem_private_key(candidate, password=None)
            return serialization.load_der_private_key(candidate, password=None)
        except (TypeError, ValueError):
            continue
    raise RuntimeError("ALIPAY_APP_PRIVATE_KEY_B64 does not contain a valid key")


def _load_certificate(data: bytes) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(data)
    except ValueError:
        return x509.load_der_x509_certificate(data)


def _load_pem_certificates(data: bytes) -> list[x509.Certificate]:
    marker = b"-----END CERTIFICATE-----"
    certificates = []
    for chunk in data.split(marker):
        if b"-----BEGIN CERTIFICATE-----" not in chunk:
            continue
        try:
            certificates.append(
                x509.load_pem_x509_certificate(chunk + marker + b"\n")
            )
        except ValueError:
            # Alipay root bundles can include SM2 certificates that older
            # cryptography/OpenSSL builds cannot decode. Root SN only uses RSA.
            continue
    if not certificates:
        certificates.append(_load_certificate(data))
    return certificates


def certificate_sn(cert: x509.Certificate) -> str:
    issuer = cert.issuer.rfc4514_string()
    source = f"{issuer}{cert.serial_number}"
    return hashlib.md5(source.encode("utf-8")).hexdigest()


def root_certificate_sn(data: bytes) -> str:
    sns = [
        certificate_sn(cert)
        for cert in _load_pem_certificates(data)
        if cert.signature_algorithm_oid.dotted_string.startswith(
            RSA_SIGNATURE_OID_PREFIX
        )
    ]
    if not sns:
        raise RuntimeError("Alipay root certificate contains no RSA certificates")
    return "_".join(sns)


def _signing_content(params: dict[str, object]) -> str:
    return "&".join(
        f"{key}={params[key]}"
        for key in sorted(params)
        if params[key] not in (None, "") and key != "sign"
    )


def _extract_raw_response_object(payload: str, response_key: str) -> tuple[dict, str]:
    key_literal = json.dumps(response_key, ensure_ascii=False)
    key_index = payload.find(key_literal)
    if key_index < 0:
        raise ValueError("Alipay response is missing response node")
    colon_index = payload.find(":", key_index + len(key_literal))
    if colon_index < 0:
        raise ValueError("Alipay response node is malformed")
    value_start = colon_index + 1
    while value_start < len(payload) and payload[value_start].isspace():
        value_start += 1
    value, consumed = json.JSONDecoder().raw_decode(payload[value_start:])
    if not isinstance(value, dict):
        raise ValueError("Alipay response node is not an object")
    return value, payload[value_start : value_start + consumed]


class AlipayDirectService:
    def __init__(self, config: AlipayDirectConfig):
        self.config = config
        self.private_key = _load_private_key(config.app_private_key)
        if not isinstance(self.private_key, rsa.RSAPrivateKey):
            raise RuntimeError("Alipay application key must be RSA")
        self.app_cert = _load_certificate(config.app_cert)
        self.alipay_public_cert = _load_certificate(config.alipay_public_cert)
        if (
            self.private_key.public_key().public_numbers()
            != self.app_cert.public_key().public_numbers()
        ):
            raise RuntimeError(
                "Alipay application private key does not match application certificate"
            )
        self.app_public_key = self.app_cert.public_key()
        self.alipay_public_key = self.alipay_public_cert.public_key()
        self.app_cert_sn = certificate_sn(self.app_cert)
        self.alipay_public_cert_sn = certificate_sn(self.alipay_public_cert)
        self.alipay_root_cert_sn = root_certificate_sn(config.alipay_root_cert)

    @staticmethod
    def _amount(value: Decimal | str | int) -> str:
        return f"{Decimal(str(value)).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP):.2f}"

    def _sign(self, content: str) -> str:
        signature = self.private_key.sign(
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def _common_params(self, *, method: str, biz_content: dict) -> dict[str, str]:
        return {
            "app_id": self.config.app_id,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "app_cert_sn": self.app_cert_sn,
            "alipay_root_cert_sn": self.alipay_root_cert_sn,
            "biz_content": json.dumps(
                biz_content,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        }

    def create_payment_url(
        self,
        *,
        out_trade_no: str,
        subject: str,
        amount: Decimal | str | int,
        product: str,
        return_url: str | None = None,
    ) -> dict:
        methods = {
            "page": ("alipay.trade.page.pay", "FAST_INSTANT_TRADE_PAY"),
            "wap": ("alipay.trade.wap.pay", "QUICK_WAP_WAY"),
        }
        if product not in methods:
            raise ValueError("Unsupported Alipay website product")
        method, product_code = methods[product]
        params = self._common_params(
            method=method,
            biz_content={
                "out_trade_no": out_trade_no,
                "product_code": product_code,
                "seller_id": self.config.seller_id,
                "subject": subject[:256],
                "total_amount": self._amount(amount),
            },
        )
        params["notify_url"] = self.config.notify_url
        params["return_url"] = return_url or self.config.return_base_url
        params["sign"] = self._sign(_signing_content(params))
        return {
            "code": 1,
            "data": {"payurl": f"{self.config.gateway_url}?{urlencode(params)}"},
        }

    def verify_callback(self, params: dict[str, str]) -> bool:
        if str(params.get("sign_type", "")).upper() != "RSA2":
            return False
        if params.get("app_id") != self.config.app_id:
            return False
        if params.get("auth_app_id") not in (None, "", self.config.app_id):
            return False
        if params.get("seller_id") != self.config.seller_id:
            return False
        if params.get("alipay_cert_sn") != self.alipay_public_cert_sn:
            return False
        if params.get("trade_status") not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return False
        if not all(
            params.get(field)
            for field in ("out_trade_no", "trade_no", "total_amount", "sign")
        ):
            return False
        try:
            self.alipay_public_key.verify(
                base64.b64decode(params["sign"], validate=True),
                _signing_content(params).encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    def _verify_response_signature(
        self,
        payload: str,
        response_key: str,
        *,
        charset: str = "utf-8",
    ) -> dict:
        parsed = json.loads(payload)
        cert_sn = parsed.get("alipay_cert_sn")
        if cert_sn != self.alipay_public_cert_sn:
            raise ValueError("Alipay response certificate serial mismatch")
        response, raw_response = _extract_raw_response_object(payload, response_key)
        signature = parsed.get("sign")
        if not signature:
            raise ValueError("Alipay response signature is missing")
        try:
            self.alipay_public_key.verify(
                base64.b64decode(signature, validate=True),
                raw_response.encode(charset),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (InvalidSignature, LookupError, UnicodeError, ValueError) as exc:
            raise ValueError("Alipay response signature is invalid") from exc
        return response

    async def query_order(
        self,
        *,
        out_trade_no: str,
        expected_amount: Decimal | str | int,
        timeout_seconds: int = 5,
        **_ignored,
    ) -> RMBOrderQueryResult:
        params = self._common_params(
            method="alipay.trade.query",
            biz_content={"out_trade_no": out_trade_no},
        )
        params["sign"] = self._sign(_signing_content(params))
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.gateway_url,
                data=params,
                timeout=timeout_seconds,
                allow_redirects=False,
            ) as response:
                payload = await response.text()
                if response.status != 200:
                    raise ValueError("Alipay order query returned a non-200 response")
        data = self._verify_response_signature(
            payload,
            "alipay_trade_query_response",
            charset=response.charset or "utf-8",
        )
        if str(data.get("code")) != "10000":
            sub_code = str(data.get("sub_code") or "")
            if sub_code in {
                "ACQ.TRADE_NOT_EXIST",
                "ACQ.TRADE_HAS_CLOSE",
                "ACQ.TRADE_STATUS_ERROR",
            }:
                return RMBOrderQueryResult(
                    status=RMBOrderQueryStatus.NOT_PAID,
                    out_trade_no=out_trade_no,
                )
            raise ValueError("Alipay order query was rejected")
        if str(data.get("out_trade_no") or "") != out_trade_no:
            raise ValueError("Alipay order query returned a different order")
        if str(data.get("seller_id") or "") != self.config.seller_id:
            raise ValueError("Alipay order query seller mismatch")
        trade_status = str(data.get("trade_status") or "")
        if trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
            return RMBOrderQueryResult(
                status=RMBOrderQueryStatus.NOT_PAID,
                out_trade_no=out_trade_no,
            )
        amount = self._amount(data.get("total_amount"))
        if amount != self._amount(expected_amount):
            raise ValueError("Alipay order query amount mismatch")
        trade_no = str(data.get("trade_no") or "")
        if not trade_no:
            raise ValueError("Alipay paid order is missing trade number")
        return RMBOrderQueryResult(
            status=RMBOrderQueryStatus.PAID,
            out_trade_no=out_trade_no,
            external_trade_no=trade_no,
            paid_amount=Decimal(amount),
        )


@lru_cache(maxsize=1)
def get_alipay_direct_service() -> AlipayDirectService:
    config = load_alipay_direct_config(required_if_enabled=False)
    if config is None:
        raise RuntimeError("Alipay direct configuration is unavailable")
    return AlipayDirectService(config)


def validate_alipay_direct_startup_config() -> bool:
    if not is_alipay_direct_enabled():
        return False
    get_alipay_direct_service.cache_clear()
    get_alipay_direct_service()
    return True
