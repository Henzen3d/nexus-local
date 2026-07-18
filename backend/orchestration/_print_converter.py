"""Script temporário: converte print() → logger em arquivos do backend."""
import re
import os

BASE = r"J:\Arquivos Osmar\Multi+\backend"

# Mapeamento de arquivo → lista de (old_print_pattern, replacement_template)
# Cada item é (regex_para_print, modo_de_logger)

def add_logger_import(filepath, content):
    """Adiciona import de logging_config se não existir."""
    if "from backend.logging_config import" in content:
        return content
    if "get_logger" in content:
        return content

    # Encontra o último import no topo do arquivo
    lines = content.split("\n")
    last_import_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            last_import_idx = i

    # Insere após o último import
    lines.insert(last_import_idx + 1, "")
    lines.insert(last_import_idx + 2, "from backend.logging_config import get_logger")
    lines.insert(last_import_idx + 3, "logger = get_logger(__name__)")
    return "\n".join(lines)


def replace_prints(content):
    """Substitui prints por logger calls com severidade apropriada."""

    # Padrões de erro (contêm "error", "erro", "falh", "Error", "fail", "Failed", "WARN")
    # Padrões de info (contêm "OK", "created", "iniciado", "concluído", "processed", "executado")
    # Default: logger.info

    lines = content.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]

        if stripped.startswith("print("):
            # Determina severidade
            lower = stripped.lower()
            is_error = any(w in lower for w in ["error", "erro", "falh", "fail", "warn", "disabled", "🚫", "⚠️"])
            is_warning = any(w in lower for w in ["warn", "⚠️", "degrad"])
            is_info_ok = any(w in lower for w in ["[ok]", "concluído", "concluido", "iniciado", "created", "processed", "executado", "reclassificado", "sintetizado", "✅"])

            if is_error and not is_warning:
                level = "logger.error"
            elif is_warning:
                level = "logger.warning"
            else:
                level = "logger.info"

            # Extrai conteúdo do print
            # Tenta f-string: print(f"...{var}...")
            print_content = stripped[len("print("):]
            # Remove parêntese final (mas cuidado com parênteses aninhados)
            depth = 0
            end_idx = -1
            for j, ch in enumerate(print_content):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    if depth == 0:
                        end_idx = j
                        break
                    depth -= 1

            if end_idx == -1:
                # Print multilinha - pula
                result.append(line)
                i += 1
                continue

            inner = print_content[:end_idx].strip()

            # Se é f-string, converte para % style
            if inner.startswith('f"') or inner.startswith("f'"):
                quote_char = inner[1]
                # Extrai a string sem o f
                str_content = inner[2:]  # remove f"
                if str_content.endswith('"') or str_content.endswith("'"):
                    str_content = str_content[:-1]

                # Converte {var} → %s e coleta args
                args = []
                pattern = r'\{([^}]+)\}'
                def replace_var(m):
                    var_expr = m.group(1)
                    # Se é uma expressão simples (variável), adiciona como arg
                    args.append(var_expr)
                    return "%s"

                converted = re.sub(pattern, replace_var, str_content)

                if args:
                    args_str = ", ".join(args)
                    if is_error or is_warning:
                        # Para erros, usa exc_info quando há exceção e
                        new_line = f'{indent}{level}("{converted}", exc_info=e)' if "exc_info" not in converted else f'{indent}{level}("{converted}")'
                        # Simplificação: se tem {e} no final, usa exc_info
                        if "e}" in str_content or "err}" in str_content or "error}" in str_content.lower():
                            # Remove o último %s que era {e} e usa exc_info
                            if converted.endswith("%s") and args[-1] in ("e", "err", "rep_err", "mem_err", "error_msg"):
                                converted = converted[:-3].rstrip()
                                args = args[:-1]
                                if args:
                                    new_line = f'{indent}{level}("{converted}", exc_info={args[-1] if args else "e"})'
                                else:
                                    new_line = f'{indent}{level}("{converted}", exc_info=e)'
                            else:
                                new_line = f'{indent}{level}("{converted}", {", ".join(args)})'
                        else:
                            new_line = f'{indent}{level}("{converted}", {args_str})'
                    else:
                        new_line = f'{indent}{level}("{converted}", {args_str})'
                else:
                    new_line = f'{indent}{level}("{converted}")'
            elif inner.startswith('"') or inner.startswith("'"):
                # String literal sem f-string
                quote_char = inner[0]
                str_content = inner[1:]
                if str_content.endswith('"') or str_content.endswith("'"):
                    str_content = str_content[:-1]
                new_line = f'{indent}{level}("{str_content}")'
            else:
                # Outros casos - mantém como info
                new_line = f'{indent}{level}("{inner}")'

            result.append(new_line)
        else:
            result.append(line)
        i += 1

    return "\n".join(result)


files_to_process = [
    "database.py",
    "memory.py",
    "providers/base.py",
    "projects/embedder.py",
    "projects/indexer.py",
    "projects/context_builder.py",
    "projects/memory_job.py",
    "projects/vector_store.py",
    "web_search/providers.py",
    "cache/manager.py",
    "ranking/quota.py",
    "routers/projects.py",
    "routers/admin.py",
    "routers/memory.py",
    "attachments/extractors.py",
    "attachments/storage.py",
    "free_registry/freellm_scraper.py",
]

for fname in files_to_process:
    fpath = os.path.join(BASE, fname.replace("/", os.sep))
    if not os.path.exists(fpath):
        print(f"SKIP (not found): {fname}")
        continue

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    print_count = content.count("print(")

    if print_count == 0:
        print(f"SKIP (no prints): {fname}")
        continue

    # Add logger import
    content = add_logger_import(fpath, content)

    # Replace prints
    content = replace_prints(content)

    print(f"WRITING: {fname} ({print_count} prints processed)")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

print("\nDONE")
