import requests

class GitHubAPI:
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }

    def get_pull_request_diff(self, owner: str, repo: str, pull_number: int) -> str:
        """Obtiene el archivo diff de un Pull Request."""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text

    def post_or_update_comment(self, owner: str, repo: str, pull_number: int, body: str, marker: str):
        """Publica un comentario en el PR o lo actualiza si ya existe uno con el marcador oculto."""
        comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pull_number}/comments"
        
        # Buscar comentarios existentes para ver si ya pusimos el reporte antes
        response = requests.get(comments_url, headers=self.headers)
        response.raise_for_status()
        comments = response.json()

        existing_comment_id = None
        for comment in comments:
            if marker in comment["body"]:
                existing_comment_id = comment["id"]
                break

        full_body = f"{body}\n\n<!-- {marker} -->"

        if existing_comment_id:
            # Actualizar comentario existente
            update_url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{existing_comment_id}"
            res = requests.patch(update_url, headers=self.headers, json={"body": full_body})
        else:
            # Crear un nuevo comentario
            res = requests.post(comments_url, headers=self.headers, json={"body": full_body})
        
        res.raise_for_status()
