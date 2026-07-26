import hmac
import hashlib

def verify_webhook_signature(request_body: bytes, signature_header: str, secret: str) -> bool:
    """Verifica la firma HMAC SHA256 enviada por GitHub en el encabezado."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    
    received_sig = signature_header.split("=")[1]
    computed_sig = hmac.new(
        secret.encode("utf-8"),
        msg=request_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_sig, received_sig)

def parse_webhook_event(event_type: str, payload: dict) -> dict:
    """Extrae la información clave del evento recibido."""
    if event_type == "pull_request":
        return {
            "action": payload.get("action"),
            "pull_number": payload.get("pull_request", {}).get("number"),
            "owner": payload.get("repository", {}).get("owner", {}).get("login"),
            "repo": payload.get("repository", {}).get("name"),
            "diff_url": payload.get("pull_request", {}).get("diff_url")
        }
    return {}
