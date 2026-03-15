import base64
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.x509.oid import NameOID


def generate_wireguard_keypair() -> tuple[str, str]:
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return (
        base64.b64encode(private_raw).decode("utf-8"),
        base64.b64encode(public_raw).decode("utf-8"),
    )


def generate_self_contained_ca(common_name: str) -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _serialize_private_key_pem(key), _serialize_certificate_pem(cert)


def generate_signed_certificate(
    *,
    ca_private_key_pem: str,
    ca_certificate_pem: str,
    common_name: str,
    san_dns_names: list[str] | None = None,
    san_ip_addresses: list[str] | None = None,
    client: bool = False,
) -> tuple[str, str]:
    ca_key = serialization.load_pem_private_key(ca_private_key_pem.encode("utf-8"), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_certificate_pem.encode("utf-8"))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage(
                [
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH
                    if client
                    else x509.oid.ExtendedKeyUsageOID.SERVER_AUTH
                ]
            ),
            critical=False,
        )
    )
    san_items: list[x509.GeneralName] = []
    for item in san_dns_names or []:
        if item:
            san_items.append(x509.DNSName(item))
    for item in san_ip_addresses or []:
        if item:
            import ipaddress

            san_items.append(x509.IPAddress(ipaddress.ip_address(item)))
    if san_items:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_items), critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    return _serialize_private_key_pem(key), _serialize_certificate_pem(cert)


def generate_opaque_client_uid() -> str:
    import os

    return base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")


def _serialize_private_key_pem(key) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _serialize_certificate_pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
