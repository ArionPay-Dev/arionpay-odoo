"""Build the Odoo module zips: copies the ArionPay Python SDK into payment_arionpay/lib/arionpay, then zips it twice.
   python3 build.py  ->  dist/payment_arionpay-20.0-1.0.0.zip       (Odoo 20)
                         dist/payment_arionpay-17.0-19.0-1.0.0.zip  (Odoo 17, 18 and 19)
   Unzip into an addons path, then install the app. The Python code is the same; only the payment method data
   and the manifest version differ."""
import os, re, shutil, zipfile, pathlib
HERE = pathlib.Path(__file__).resolve().parent
SDK = HERE.parent / "arionpay-python" / "src" / "arionpay"
MOD = HERE / "payment_arionpay"
lib = MOD / "lib"
if (lib / "arionpay").exists():
    shutil.rmtree(lib / "arionpay")
lib.mkdir(exist_ok=True)
(lib / "__init__.py").write_text("# Bundled ArionPay Python SDK (MIT), so the module needs no pip install.\n")
shutil.copytree(SDK, lib / "arionpay", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copy(HERE.parent / "arionpay-python" / "LICENSE", lib / "arionpay" / "LICENSE")
(HERE / "dist").mkdir(exist_ok=True)
for old in (HERE / "dist").glob("payment_arionpay-*.zip"):
    old.unlink()
manifest = (MOD / "__manifest__.py").read_text()
variants = {
    "payment_arionpay-20.0-1.0.0.zip": ("20.0.1.0.0", "payment_method_data.xml"),
    "payment_arionpay-17.0-19.0-1.0.0.zip": ("1.0.0", "payment_method_data_17_19.xml"),
}
for name, (version, method_data) in variants.items():
    out = HERE / "dist" / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(MOD):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for f in sorted(files):
                p = pathlib.Path(root) / f
                rel = str(p.relative_to(MOD))
                if f.endswith(".pyc") or rel in ("__manifest__.py", "data/payment_provider_data.xml", "data/payment_method_data.xml", "data/payment_method_data_17_19.xml"):
                    continue
                z.write(p, "payment_arionpay/" + rel)
        man = re.sub(r'"version": "[^"]+"', f'"version": "{version}"', manifest)
        provider_data = (MOD / "data" / "payment_provider_data.xml").read_text()
        if version.startswith("20."):
            # Odoo 20 has a shared redirect form, and a template added by a module that loads before `website`
            # fails there (website makes ir.ui.view.visibility required); so no template of our own.
            man = man.replace('        "views/payment_arionpay_templates.xml",\n', "")
            provider_data = provider_data.replace('ref="redirect_form"', 'ref="payment.generic_redirect_form"')
        z.writestr("payment_arionpay/__manifest__.py", man)
        z.writestr("payment_arionpay/data/payment_provider_data.xml", provider_data)
        z.writestr("payment_arionpay/data/payment_method_data.xml", (MOD / "data" / method_data).read_text())
    print(out, os.path.getsize(out), "bytes")
