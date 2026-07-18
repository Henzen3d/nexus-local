import sys
import os
import sqlite3
import uuid
from dotenv import load_dotenv

load_dotenv()

# Ensure we can import from the backend directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.auth import hash_password
from backend.database import DB_PATH

def main():
    args = sys.argv[1:]
    clean_mode = False
    if "--clean" in args:
        clean_mode = True
        args.remove("--clean")

    if len(args) < 2:
        print("Uso: python reset_admin_pwd.py <username> <new_password> [--clean]")
        sys.exit(1)
        
    username = args[0].strip().lower()
    new_password = args[1]
    
    if not username or not new_password:
        print("Erro: Usuário e senha não podem ser vazios.")
        sys.exit(1)
        
    hashed = hash_password(new_password)
    
    print(f"Conectando ao banco de dados: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if clean_mode:
        print("Limpando todos os usuários existentes...")
        cursor.execute("DELETE FROM users")
        conn.commit()
    
    # Verificar se o usuário existe
    cursor.execute("SELECT id, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    
    if not row:
        print(f"Usuário '{username}' não encontrado. Criando novo usuário como administrador...")
        user_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (user_id, username, hashed)
        )
        conn.commit()
        role = "admin"
    else:
        user_id, role = row
        # Atualizar senha
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hashed, user_id)
        )
        conn.commit()
    
    conn.close()
    print(f"Sucesso! O usuário '{username}' ({role}) está configurado com a nova senha.")

if __name__ == "__main__":
    main()
