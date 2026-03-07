from pathlib import Path

MAX_FILE_SIZE = 1024 * 1024 * 10  # 10MB

def resolve_path(base: str | Path, path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    return Path(base).resolve() / path


def check_file_size(path: Path) -> bool:
    if path.stat().st_size > MAX_FILE_SIZE:
        return False
    return True


def is_binary_file(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(1024)
    except Exception as e:
        print(f"Error checking file type: {e}")
        return False

def get_relative_path(path: str, cwd: Path) -> str:
    try:
        p = Path(path)
    except ValueError:
        return path  # Return original if path is invalid

    if cwd:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            pass

    return str(p)


if __name__ == "__main__":
    print(resolve_path("/home/user", "file.txt"))
    print(resolve_path("/home/user", "/etc/passwd"))
    print(resolve_path("/home/user", "../etc/passwd"))
