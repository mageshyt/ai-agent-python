import tiktoken
def get_tokenizer(model:str="gpt-4"):
    try:
        encoding = tiktoken.encoding_for_model(model)
        return encoding.encode
    except ImportError:
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding.encode

def count_tokens(text:str, model:str="gpt-4") -> int:
    tokenizer = get_tokenizer(model)
    tokens = tokenizer(text)

    return estimate_token_count(text) if tokens is None else len(tokens)

def estimate_token_count(text:str) -> int:
    return max(1,len(text) // 4)  # Rough estimate: 1 token ~ 4 characters

def truncate_text_by_tokens(
    text:str,
    max_tokens:int,
    model:str="gpt-4",
    suffix:str = "\n...[truncated]",
    preserve_lines:bool = True
) -> str:
    current_tokens = count_tokens(text, model)
    if current_tokens <= max_tokens:
        return text
    suffix_tokens = count_tokens(suffix, model)
    allowed_tokens = max_tokens - suffix_tokens

    if allowed_tokens <= 0:
        return suffix[:max_tokens]

    if preserve_lines:
        return _truncate_by_lines(text, allowed_tokens, model, suffix)
    else:
        return _truncate_by_chars(text, allowed_tokens, model, suffix)


def _truncate_by_lines(text:str, allowed_tokens:int, model:str="gpt-4", suffix:str = "\n...[truncated]") -> str:
    lines = text.splitlines()
    truncated_text = ""
    current_tokens = 0

    for line in lines:
        line_tokens = count_tokens(line + "\n", model)
        if current_tokens + line_tokens > allowed_tokens:
            break
        truncated_text += line + "\n"
        current_tokens += line_tokens

    return truncated_text.rstrip("\n") + suffix

def _truncate_by_chars(text:str, allowed_tokens:int, model:str="gpt-4", suffix:str = "\n...[truncated]") -> str:
    low,high = 0, len(text)

    while low < high:
        mid = (low + high) // 2
        if count_tokens(text[:mid] + suffix, model) <= allowed_tokens:
            low = mid + 1
        else:
            high = mid


    return text[:low-1] + suffix
