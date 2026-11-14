# Payment Provider: ArionPay (crypto) for Odoo

Crypto payments (Bitcoin, USDT, Litecoin, Ethereum, TRON and more) for Odoo through [ArionPay](https://arionpay.com): eCommerce checkout, invoice and sales order payment links, and the customer portal. The money goes straight to your own wallet: ArionPay never holds it.

For Odoo 17, 18, 19 and 20. Tested on Odoo 18.0, 19.0 and 20.0 (Community) with eCommerce, PostgreSQL 16 and Python 3.12: the same 22 checks on each. The tests covered checkout, coming back before and after paying, a lost webhook, "payment seen" then confirmed, payment tolerance, Payment Radar, late payments, a wrong amount and webhook checks. Odoo 17 uses the same payment interface as 18 but was not run here. The module brings its own copy of the ArionPay Python library, so there is nothing to `pip install`.

Two zips, with the same code and different data files for each version:

- **Odoo 20**: `payment_arionpay-20.0-1.0.0.zip`
- **Odoo 17, 18 and 19**: `payment_arionpay-17.0-19.0-1.0.0.zip`

## Install

1. Unzip the zip for your Odoo version into a folder on your Odoo addons path (or your Odoo.sh repository), restart Odoo and update the apps list.
2. **Apps**: install **Payment Provider: ArionPay (crypto)**.
3. **Invoicing / Website > Configuration > Payment Providers > ArionPay (crypto)**: fill in the fields below and publish it. While you try it, keep Odoo 20's **Live** switch off, or set **State** to **Test Mode** on Odoo 17 to 19.

| Field | Where in the ArionPay dashboard | Starts with |
| --- | --- | --- |
| API Key | Open your store, **API key** | `pk_` |
| API Secret | Open your store, **API secret** (asks for your authenticator code) | `sk_` |
| Webhook Signing Secret | **Webhooks** page, **signing secret** | `whsec_` |
| ArionPay Address | leave empty | |

Test mode makes test invoices (no real money). For real payments, switch **Live** on (Odoo 20) or set **State** to **Enabled** (Odoo 17 to 19). Nothing to paste into ArionPay: each invoice tells ArionPay where to send its payment updates (`/payment/arionpay/webhook` on your Odoo).

Also check, in your ArionPay store settings, that **Old ArionPay (v1) integration compatibility** is off.

## How payments change

- At checkout the customer chooses **Crypto (Bitcoin, USDT and more)**, presses **Pay now** and goes to the ArionPay page.
- When ArionPay sees the payment on the network, the transaction is **Pending**. When ArionPay confirms the full payment, it is **Done**, and Odoo confirms the sales order as usual. The transaction message names the ArionPay invoice, the coin and network, and notes such as "paid late".
- When the customer comes back, the module asks ArionPay directly, so a lost webhook is caught there too. Then Odoo's payment status page takes over.
- A payment that is not exact goes to **Payment Radar** in your ArionPay dashboard. A small difference inside your store's payment tolerance (default 1%) is accepted automatically; anything else you decide. If you accept it, the transaction is done here too.
- A late payment still completes the transaction.
- A transaction is completed only by the invoice made for it. It must be test or live like the provider, and the paid amount and currency must match. Odoo 19 and 20 check that in their core; on 17 and 18 the module checks it itself. A mismatch becomes an error, never a completed payment. Repeated updates change nothing once a transaction is done.

## Good to know

- ArionPay takes USD, EUR, GBP, CAD, AUD, CHF, JPY, TRY, AED, INR, BRL, RUB, CNY, SGD, HKD, KRW, MXN, PLN, SEK, NOK, ZAR. Odoo offers the provider only for these currencies.
- Refunds are made from your own wallet; then record the refund in Odoo by hand.
- The module sends ArionPay the transaction reference, amount and currency. It does not send the customer's name or email.
- Like Odoo's other providers, the keys are visible to system administrators only (masked fields).
