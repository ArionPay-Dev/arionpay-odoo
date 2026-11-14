# Fiat currencies ArionPay invoices can be priced in.
SUPPORTED_CURRENCIES = (
    "USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "TRY", "AED", "INR", "BRL",
    "RUB", "CNY", "SGD", "HKD", "KRW", "MXN", "PLN", "SEK", "NOK", "ZAR",
)

DEFAULT_PAYMENT_METHOD_CODES = {"arionpay"}

# ArionPay invoice statuses that can still become paid.
OPEN_STATUSES = ("pending", "paid_partial", "claim_pending")

MAX_BODY_BYTES = 262144
