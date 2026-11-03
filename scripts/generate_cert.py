"""Generate a self-signed HTTPS certificate for LAN phone camera access.

Browsers permit getUserMedia only in a secure context. A plain http://LAN_IP
page is not secure. This certificate includes localhost, 127.0.0.1, the Windows
hostname and every detected private IPv4 address as Subject Alternative Names.
The phone must trust certs/sih-26037.crt (or the user must explicitly accept the
browser warning) before camera permission can be granted.
"""
from __future__ import annotations

import ipaddress
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import local_ipv4_addresses  # noqa: E402

CERT_DIR = ROOT / "certs"
CERT_PATH = CERT_DIR / "sih-26037.crt"
KEY_PATH = CERT_DIR / "sih-26037.key"


def main() -> int:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Gujarat"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Vadodara"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SIH-26037"),
        x509.NameAttribute(NameOID.COMMON_NAME, "SIH-26037 Local Dashboard"),
    ])
    san_names = [x509.DNSName("localhost"), x509.DNSName(socket.gethostname()),
                 x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    lan_ips = local_ipv4_addresses()
    for ip in lan_ips:
        try:
            san_names.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Certificate: {CERT_PATH}")
    print(f"Private key: {KEY_PATH}")
    print(f"LAN SANs: {', '.join(lan_ips) if lan_ips else 'none detected; localhost only'}")
    print("Install/trust the .crt on the Android phone, then set SIH_USE_HTTPS=1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
