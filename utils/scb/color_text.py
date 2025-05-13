class ColorText:
    """Lightweight ANSI color helper. Only used for console debugging logs.
    If your terminal doesn't support ANSI colors you can ignore these.
    """

    RESET = "\033[0m"
    END = RESET  # alias kept for compatibility with existing code

    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m" 