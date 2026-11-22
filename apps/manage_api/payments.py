"""Cổng thanh toán cho tiền cọc đặt bàn.

Hiện chỉ có nhà cung cấp GIẢ LẬP (mock): không thu tiền thật, không lưu thông tin thẻ. Giao diện `PaymentProvider`
để sau này thay bằng cổng thật (VNPay/MoMo...) mà không phải viết lại luồng đặt bàn."""
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class Charge:
    provider: str
    ref: str
    status: str  # PENDING | PAID


class PaymentProvider(Protocol):
    name: str
    is_real: bool

    def create_charge(self, amount: int, reference: str) -> Charge: ...
    def confirm(self, ref: str) -> Charge: ...
    def refund(self, ref: str, amount: int) -> str: ...


class MockPaymentProvider:
    name = "mock"
    is_real = False

    def create_charge(self, amount: int, reference: str) -> Charge:
        return Charge(self.name, f"mock_{uuid4().hex[:16]}", "PENDING")

    def confirm(self, ref: str) -> Charge:
        """Giả lập khách đã trả: luôn thành công. Chỉ gọi được khi nhà cung cấp không phải thật."""
        return Charge(self.name, ref, "PAID")

    def refund(self, ref: str, amount: int) -> str:
        return f"mock_refund_{uuid4().hex[:12]}"


def provider_for(name: str) -> PaymentProvider:
    if name == "mock":
        return MockPaymentProvider()
    raise ValueError(f"Chưa hỗ trợ nhà cung cấp thanh toán: {name}")
