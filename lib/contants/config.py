CONFIG_FILE_NAME = "config.toml"
AGENT_MD_FILE_NAME = "agent.md"
APP_NAME = "cyberowl-agent"

# Branding and character/persona settings for the CLI experience.
AGENT_DISPLAY_NAME = "CYBEROWL"
AGENT_ASCII_FONT = "ansi_shadow"
AGENT_TAGLINE = "Command-line interface"
AGENT_CHARACTER = "Precise, practical coding partner. Prioritize correctness, safety, and clear execution."

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "coverage",
}

BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
}

SAFE_PATTERNS = [
    r"^(ls|dir|pwd|cd|echo|cat|head|tail|less|more|find|grep|awk|sed|cut|sort|uniq|wc|diff|du|df|free|uptime|whoami|id)\b",
    r"^(find|locate|which|whereis|file|stat)(\s|$)",
    # read-only commands
    r"^git\s+(status|log|diff|show|branch|remote|tag)(\s|$)",
    r"^(npm|yarn|pnpm)\s+(list|ls|outdated)(\s|$)",
    r"^pip\s+(list|show|freeze)(\s|$)",
    r"^cargo\s+(tree|search)(\s|$)",
    # text searching/processing commands
    r"^(grep|awk|sed|cut|sort|uniq|tr|diff|comm)(\s|$)",
    # system info
    r"^(date|cal|uptime|whoami|id|groups|hostname|uname)(\s|$)",
    r"^(env|printenv|set)$",
    # Process info
    r"^(ps|top|htop|pgrep)(\s|$)",  r"^(date|cal|uptime|whoami|id|groups|hostname|uname)(\s|$)",
    r"^(env|printenv|set)$",
    # Process info
    r"^(ps|top|htop|pgrep)(\s|$)",
]

BLOCKED_FILES = [".env", ".env.*", "*.pem", "*.key", "credentials.json", "secrets.*"]

MAX_FILE = 1000  # maximum number of files to read in grep tool to prevent excessive memory usage
MAX_CONTENT_SIZE = (
    1024 * 100
)  # 100kb - maximum content size to read from files or web responses to prevent excessive memory usage
MIN_MESSAGE_LIMIT = 10  # min number of message needed for summarization
CONTEXT_RESET_SIZE = 0.8  # percentage of messages to retain when resetting context, must be between 0 and 1
