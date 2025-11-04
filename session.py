from pathlib import Path
import re

def load_env(start: str = __file__, max_depth: int = 10) -> Path:
    root = Path(start)
    root = root if root.is_dir() else root.parent
    env = root / ".env"
    depth = 0

    while (not env.exists()):
        env = env.parent.parent / ".env"
        depth += 1

        if depth > max_depth:
            raise RecursionError("Maximum depth reached and no .env file found")

    return env

def create_cookie_header(env_file: Path) -> str:
    cookies = []
    pattern = re.compile(r'\s*([^ ]*)\s*=\s*([^\n]+)')
    with env_file.open('r', errors='ignore') as file:
        for line in file.readlines():
            if line.startswith('#'):
                continue

            syntax_match = pattern.match(line)
            if not syntax_match:
                continue

            key, value = syntax_match.groups()

            cookies.append(f'{key}:{value}')
    return ';'.join(cookies)
