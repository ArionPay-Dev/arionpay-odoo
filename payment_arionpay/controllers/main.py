import json


from odoo import http
from odoo.http import request

from odoo.addons.payment_arionpay import const
from odoo.addons.payment_arionpay.lib.arionpay import ArionPayError, SignatureError, is_test_event, verify_webhook
from odoo.addons.payment_arionpay.models.payment_transaction import RETURN_URL, WEBHOOK_URL

try:  # Odoo 19+
    from odoo.addons.payment.logging import get_payment_logger

    _logger = get_payment_logger(__name__)
except ImportError:  # Odoo 17/18
    import logging

    _logger = logging.getLogger(__name__)


class ArionPayController(http.Controller):

    @http.route(WEBHOOK_URL, type="http", auth="public", methods=["POST"], csrf=False, save_session=False)
    def arionpay_webhook(self, **_kwargs):
        """Signed ArionPay webhook. Trusted only by the ArionPay-Signature over the exact body."""
        raw = request.httprequest.get_data(cache=False, as_text=False)
        if len(raw) > const.MAX_BODY_BYTES:
            return self._json(413, {"error": "too large"})
        try:
            peek = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self._json(400, {"error": "not json"})
        invoice = ((peek.get("data") or {}).get("invoice") or {}) if isinstance(peek, dict) else {}
        reference = (invoice.get("metadata") or {}).get("odoo_reference")
        tx_sudo = request.env["payment.transaction"].sudo().search([("reference", "=", reference), ("provider_code", "=", "arionpay")], limit=1) if reference else None
        # The secret of the transaction's provider (or of any ArionPay provider, for "Send test webhook").
        provider = tx_sudo.provider_id if tx_sudo else request.env["payment.provider"].sudo().search([("code", "=", "arionpay")], limit=1)
        secret = (provider.arionpay_webhook_secret or "").strip() if provider else ""
        if not secret:
            return self._json(503, {"error": "webhook secret not set"})
        try:
            event = verify_webhook(raw, request.httprequest.headers.get("ArionPay-Signature"), secret)
        except SignatureError as error:
            _logger.warning("ArionPay webhook refused: %s", error)
            return self._json(401, {"error": "invalid signature"})
        if is_test_event(event):
            _logger.info("ArionPay test webhook received (%s). Nothing changed.", event.get("type"))
            return self._json(200, {"received": True, "test": True})
        invoice = event["data"]["invoice"]
        meta = invoice.get("metadata") or {}
        if not tx_sudo or meta.get("odoo_site") != provider._arionpay_site_id():
            return self._json(200, {"received": True, "ignored": "not a payment of this database"})
        if bool(invoice.get("test")) != provider._arionpay_is_test():
            return self._json(409, {"error": "test/live mismatch"})
        self._feed(tx_sudo, {"reference": reference, "event": event["type"], "source": "webhook", "invoice": invoice})
        return self._json(200, {"received": True})

    @http.route(RETURN_URL, type="http", auth="public", methods=["GET", "POST"], csrf=False, save_session=False)
    def arionpay_return(self, ref=None, **_kwargs):
        """The customer came back from the ArionPay page: a signed invoice read (never the URL) updates the
        transaction, then Odoo's payment status page takes over."""
        tx_sudo = request.env["payment.transaction"].sudo().search([("reference", "=", ref), ("provider_code", "=", "arionpay")], limit=1) if ref else None
        if tx_sudo and tx_sudo.provider_reference:
            try:
                invoice = tx_sudo.provider_id._arionpay_client().get_invoice(tx_sudo.provider_reference)
            except ArionPayError as error:
                _logger.warning("ArionPay read failed for %s: %s", ref, error)
                invoice = None
            if invoice and invoice.get("status") in ("paid", *const.OPEN_STATUSES):
                self._feed(tx_sudo, {"reference": ref, "event": "invoice.paid" if invoice["status"] == "paid" else "invoice.pending", "source": "signed read on return", "invoice": invoice})
        return request.redirect("/payment/status")

    @staticmethod
    def _feed(tx_sudo, data):
        """Hand verified payment data to Odoo's payment engine, whichever version it is."""
        if hasattr(tx_sudo, "_record"):  # Odoo 20: queued and processed under a lock
            tx_sudo._record(data)
        elif hasattr(tx_sudo, "_search_by_reference"):  # Odoo 19
            tx_sudo._process("arionpay", data)
        else:  # Odoo 17/18
            request.env["payment.transaction"].sudo()._handle_notification_data("arionpay", data)

    @staticmethod
    def _json(status, body):
        return request.make_json_response(body, status=status)
