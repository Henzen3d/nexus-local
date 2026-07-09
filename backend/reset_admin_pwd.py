import sys
import os
import sqlite3

# Ensure we can import from the backend directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.auth import hash_password
from backend.database import DB_PATH

def main():
    if len(sys.argv) < 3:
        print("Uso: python reset_admin_pwd.py <username> <new_password>")
        sys.exit(1)
        
    username = sys.argv[1].strip().lower()
    new_password = sys.argv[2]
    
    if not username or not new_password:
        print("Erro: Usuário e senha não podem ser vazios.")
        sys.exit(1)
        
    hashed = hash_password(new_password)
    
    print(f"Conectando ao banco de dados: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Verificar se o usuário existe
    cursor.execute("SELECT id, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    
    if not row:
        print(f"Erro: Usuário '{username}' não encontrado no banco de dados.")
        # Listar usuários disponíveis
        cursor.execute("SELECT username, role FROM users")
        users = cursor.fetchall()
        print("Usuários cadastrados:")
        for u, r in users:
            print(f"  - {u} ({r})")
        conn.close()
        sys.exit(1)
        
    user_id, role = row
    
    # Atualizar senha
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hashed, user_id)
    )
    conn.commit()
    conn.close()
    
    print(f"Sucesso! A senha do usuário '{username}' ({role}) foi redefinida com sucesso.")

if __name__ == "__main__":
    main()
