import ssl
import os


def refresh_ca_bundle(plugin_dir: str, cert_encoding_filter: str = "") -> tuple:
    """
    Export Windows CA certificates to a PEM file inside the plugin directory.
    Returns (path, cert_count). Raises on write failure.
    """
    pem_path = os.path.join(plugin_dir, "ca_bundle.pem")
    certs = list(ssl.enum_certificates("ROOT")) + list(ssl.enum_certificates("CA"))
    pem_data = []
    for cert_bytes, encoding, trust in certs:
        if encoding == cert_encoding_filter:
            try:
                pem_data.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
            except Exception:
                continue
    with open(pem_path, "w", encoding="utf-8") as f:
        f.write("\n".join(pem_data))
    return pem_path, len(pem_data)
