import re
from lib.contants.config import DANGEROUS_PATTERNS, SAFE_PATTERNS


def is_safe_command(command:str)->bool:
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False

def is_dangerous_command(command:str) ->bool:
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern,command,re.IGNORECASE):
            return True
    return False

