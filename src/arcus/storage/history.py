import sqlite3

class HistoryStorage:
    def __init__(self, db_path: str = "arcus_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Crea la tabla de historial si no existe."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner TEXT,
                    repo TEXT,
                    pull_number INTEGER,
                    commit_sha TEXT,
                    status TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_execution(self, owner: str, repo: str, pull_number: int, commit_sha: str, status: str):
        """Guarda un registro de ejecución en la base de datos."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO execution_history (owner, repo, pull_number, commit_sha, status)
                VALUES (?, ?, ?, ?, ?)
            """, (owner, repo, pull_number, commit_sha, status))
            conn.commit()

    def get_history(self, owner: str, repo: str, pull_number: int):
        """Recupera el historial de ejecuciones para un PR específico."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT commit_sha, status, timestamp FROM execution_history
                WHERE owner = ? AND repo = ? AND pull_number = ?
                ORDER BY timestamp DESC
            """, (owner, repo, pull_number))
            return cursor.fetchall()
