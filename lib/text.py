import tiktoken
def get_tokenizer(model:str):
    try:
        encoding = tiktoken.encoding_for_model(model)
        return encoding.encode
    except ImportError:
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding.encode

def count_tokens(text:str, model:str) -> int:
    tokenizer = get_tokenizer(model)
    tokens = tokenizer(text)

    return estimate_token_count(text) if tokens is None else len(tokens)

def estimate_token_count(text:str) -> int:
    return max(1,len(text) // 4)  # Rough estimate: 1 token ~ 4 characters
