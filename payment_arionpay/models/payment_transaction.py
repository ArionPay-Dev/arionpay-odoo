from urllib.parse import parse_qsl, urlsplit

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

try:  # Odoo 19+
    from odoo.tools import urls

    _join = urls.urljoin
except ImportError:  # Odoo 17/18
    from werkzeug import urls

    _join = urls.url_join

from odoo.addons.payment_arionpay import const
from odoo.addons.payment_arionpay.lib.arionpay import ArionPayError

try:  # Odoo 19+
    from odoo.addons.payment.logging import get_payment_logger

    _logger = get_payment_logger(__name__)
except ImportError:  # Odoo 17/18
    import logging

    _logger = logging.getLogger(__name__)

RETURN_URL = "/payment/arionpay/return"
WEBHOOK_URL = "/payment/arionpay/webhook"


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_specific_rendering_values(self, processing_values):
        """Override of `payment`: create the ArionPay invoice and redirect the customer to its page.

        Note: self.ensure_one() from `_get_processing_values`.
        """
        if self.provider_code != "arionpay":
            return super()._get_specific_rendering_values(processing_values)
        provider = self.provider_id
        base_url = provider.get_base_url()
        amount = f"{self.amount:.2f}"
        test = provider._arionpay_is_test()
        try:
            invoice = provider._arionpay_client().create_invoice(
                amount=amount,
                currency=self.currency_id.name,
                order_id=self.reference,
                description=self.reference,
                success_url=f"{_join(base_url, RETURN_URL)}?ref={self.reference}",
                cancel_url=f"{_join(base_url, RETURN_URL)}?ref={self.reference}",
                callback_url=_join(base_url, WEBHOOK_URL),
                metadata={
                    "odoo_reference": self.reference,
                    "odoo_amount": amount,
                    "odoo_currency": self.currency_id.name,
                    "odoo_site": provider._arionpay_site_id(),
                    "platform": "odoo",
                },
                # One ArionPay invoice per Odoo transaction (a retried request returns the same invoice).
                idempotency_key=f"odoo-{provider._arionpay_site_id()}-{self.reference}-{amount}{self.currency_id.name}{'-test' if test else ''}",
                test=test,
            )
        except ArionPayError as error:
            _logger.error("could not create the ArionPay invoice for %s: %s", self.reference, error)
            self._set_error(_("The crypto payment could not be started right now. Please try again in a minute."))
            return {}
        self.provider_reference = invoice["id"]
        return {
            "api_url": invoice["invoiceUrl"],
            "http_method": "get",
            "url_params": dict(parse_qsl(urlsplit(invoice["invoiceUrl"]).query)),  # GET form: keep the URL's own parameters
        }

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment`: the Odoo reference travels in the invoice metadata."""
        if provider_code != "arionpay":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("reference")

    # --- Odoo 19 and 20: payment data -> _extract_reference / _apply_updates / _extract_amount_data (core checks the amount)

    def _apply_updates(self, payment_data):
        """Override of `payment` (Odoo 19+): update the transaction from a verified ArionPay invoice."""
        if self.provider_code != "arionpay":
            super()._apply_updates(payment_data)
            return
        self._arionpay_apply(payment_data)

    # --- Odoo 17 and 18: notification data -> _get_tx_from_notification_data / _process_notification_data

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Override of `payment` (Odoo 17/18): find the transaction by its reference."""
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "arionpay" or len(tx) == 1:
            return tx
        tx = self.search([("reference", "=", notification_data.get("reference")), ("provider_code", "=", "arionpay")])
        if not tx:
            raise ValidationError("ArionPay: " + _("No transaction found matching reference %s.", notification_data.get("reference")))
        return tx

    def _process_notification_data(self, notification_data):
        """Override of `payment` (Odoo 17/18). These versions have no core amount check, so it is done here."""
        super()._process_notification_data(notification_data)
        if self.provider_code != "arionpay":
            return
        invoice = notification_data.get("invoice") or {}
        if notification_data.get("event") == "invoice.paid" or invoice.get("status") == "paid":
            paid = round(float(invoice.get("amountFiat") or 0), 2)
            if self.currency_id.compare_amounts(paid, round(self.amount, 2)) != 0 or invoice.get("currency") != self.currency_id.name:
                self._set_error(_("The amount or currency paid at ArionPay doesn't match this transaction."), extra_allowed_states=("done",))
                return
        self._arionpay_apply(notification_data)

    # --- shared

    def _arionpay_apply(self, payment_data):
        """Update the transaction from a verified ArionPay invoice.

        `payment_data` is built by the controller from a signed webhook or a signed invoice read:
        {"reference", "event", "source", "invoice"}. ArionPay alone decides whether an invoice is paid.
        """
        invoice = payment_data.get("invoice") or {}
        if invoice.get("id") != self.provider_reference:
            _logger.warning("ArionPay invoice %s is not the one made for %s; ignored", invoice.get("id"), self.reference)
            return
        if bool(invoice.get("test")) != self.provider_id._arionpay_is_test():
            _logger.warning("ArionPay invoice %s: test/live mode differs from the provider; ignored", invoice.get("id"))
            return
        event = payment_data.get("event")
        status = invoice.get("status")
        if event == "invoice.paid" or status == "paid":
            notes = []
            if invoice.get("asset"):
                notes.append(f"{invoice.get('paidCrypto', '')} {invoice['asset']}{' on ' + invoice['network'] if invoice.get('network') else ''}".strip())
            for flag, text in (("late", "paid late"), ("underpaidWithinTolerance", "slightly under, inside the payment tolerance"), ("overpaid", "overpaid"), ("manual", "accepted by hand in ArionPay")):
                if invoice.get(flag):
                    notes.append(text)
            message = f"ArionPay invoice {invoice['id']} paid" + (f" ({'; '.join(notes)})" if notes else "") + f" [{payment_data.get('source', 'webhook')}]"
            self._set_done(state_message=("[TEST] " if invoice.get("test") else "") + message)
        elif event in ("invoice.pending", "invoice.partial") or status in const.OPEN_STATUSES:
            self._set_pending(state_message=f"ArionPay: payment seen for invoice {invoice['id']}, waiting for network confirmations.")
        else:
            # Expired or "needs review" (Payment Radar): nothing changes here; a late payment or the merchant's
            # decision in ArionPay still completes the transaction.
            _logger.info("ArionPay %s for invoice %s (%s): no change", event, invoice.get("id"), status)

    def _extract_amount_data(self, payment_data):
        """Override of `payment`: the paid invoice's price, checked by Odoo against the transaction."""
        if self.provider_code != "arionpay":
            return super()._extract_amount_data(payment_data)
        invoice = payment_data.get("invoice") or {}
        return {
            "amount": float(invoice.get("amountFiat") or 0),
            "currency_code": invoice.get("currency"),
            "precision_digits": 2,
        }
