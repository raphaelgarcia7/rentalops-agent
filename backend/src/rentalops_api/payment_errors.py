"""Safe errors for the financial boundary."""


class PaymentError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def invalid(message: str) -> PaymentError:
    return PaymentError(422, "invalid_payment", message)


def conflict(code: str = "version_conflict") -> PaymentError:
    return PaymentError(
        409,
        code,
        "Os dados financeiros ou comerciais mudaram. Consulte a versão atual; "
        "seu formulário foi mantido.",
    )
