"""Gera hash de senha para configurar o login no Streamlit Secrets."""

import getpass
import hashlib
import secrets


def build_password_hash(password: str, iterations: int = 260000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def main() -> None:
    password = getpass.getpass("Senha: ")
    confirmation = getpass.getpass("Confirmar senha: ")
    if password != confirmation:
        raise SystemExit("As senhas nao conferem.")
    if not password:
        raise SystemExit("A senha nao pode ficar em branco.")
    print(build_password_hash(password))


if __name__ == "__main__":
    main()
