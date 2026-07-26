import time
import jwt
import requests

def generate_jwt(app_id: str, private_key: str) -> str:
    """Genera un JSON Web Token (JWT) para autenticarse como GitHub App."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": app_id
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    return encoded_jwt

def get_installation_token(app_id: str, private_key: str, installation_id: str) -> str:
    """Solicita un token de acceso de instalación usando el JWT."""
    jwt_token = generate_jwt(app_id, private_key)
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()["token"
