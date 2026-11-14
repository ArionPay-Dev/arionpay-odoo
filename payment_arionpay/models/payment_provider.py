import hashlib

from odoo import fields, models, release

from odoo.addons.payment_arionpay import const
from odoo.addons.payment_arionpay.lib.arionpay import DEFAULT_BASE_URL, ArionPay


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("arionpay", "ArionPay")], ondelete={"arionpay": "set default"}
    )
    arionpay_api_key = fields.Char(
        string="ArionPay API Key",
        help="ArionPay dashboard > your store > API key (starts with pk_).",
        copy=False,
        groups="base.group_system",
    )
    arionpay_api_secret = fields.Char(
        string="ArionPay API Secret",
        help="ArionPay dashboard > your store > API secret (starts with sk_).",
        copy=False,
        groups="base.group_system",
    )
    arionpay_webhook_secret = fields.Char(
        string="ArionPay Webhook Signing Secret",
        help="ArionPay dashboard > Webhooks > signing secret (starts with whsec_). Nothing to paste "
        "into ArionPay: every invoice tells ArionPay where to send its payment updates.",
        copy=False,
        groups="base.group_system",
    )
    arionpay_base_url = fields.Char(
        string="ArionPay Address",
        help="Leave empty unless ArionPay tells you otherwise.",
        copy=False,
        groups="base.group_system",
    )

    def _get_supported_currencies(self):
        """Override of `payment` to return the currencies ArionPay invoices can be priced in."""
        supported = super()._get_supported_currencies()
        if self.code == "arionpay":
            supported = supported.filtered(lambda c: c.name in const.SUPPORTED_CURRENCIES)
        return supported

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        self.ensure_one()
        if self.code != "arionpay":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _arionpay_is_test(self):
        """Test invoices (no real money) unless the provider is live.

        Odoo 20 has an `is_live` switch; Odoo 17 to 19 have `state` ("test" = test mode)."""
        self.ensure_one()
        if "is_live" in self._fields:
            return not self.is_live
        return self.state != "enabled"

    def _arionpay_client(self):
        """The ArionPay client for this provider (signed requests)."""
        self.ensure_one()
        module = self.env.ref("base.module_payment_arionpay", raise_if_not_found=False)
        return ArionPay(
            api_key=(self.arionpay_api_key or "").strip(),
            api_secret=(self.arionpay_api_secret or "").strip(),
            webhook_secret=(self.arionpay_webhook_secret or "").strip(),
            base_url=(self.arionpay_base_url or "").strip() or DEFAULT_BASE_URL,
            app_info=f"odoo/{release.version} payment_arionpay/{module.installed_version if module else '?'}",
        )

    def _arionpay_site_id(self):
        """Short id of this Odoo database, so two databases on one ArionPay store never touch each other's payments."""
        icp = self.env["ir.config_parameter"].sudo()
        # Odoo 20 has typed getters (get_str); older versions use get_param.
        uuid = icp.get_str("database.uuid") if hasattr(icp, "get_str") else icp.get_param("database.uuid", "")
        return hashlib.sha256(f"odoo|{uuid}".encode()).hexdigest()[:12]
