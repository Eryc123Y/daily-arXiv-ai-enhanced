"""Summary instructions shared by the API mode and the Claude Code subagents."""

FIELD_GUIDE = {
    "tldr": "one or two sentences: what the paper does and what it finds",
    "motivation": "the problem addressed and what existing work lacks",
    "method": "the core approach and its key design choices",
    "result": "the main findings, keeping key numbers, datasets and baselines",
    "conclusion": "the takeaway and its significance",
}


def instructions(language):
    fields = "\n".join(f"- {name}: {guide}" for name, guide in FIELD_GUIDE.items())
    return (
        "You are a professional paper analyst. Summarise an arXiv paper from its title "
        f"and abstract in {language}, filling five fields:\n{fields}\n\n"
        "Be concise, specific and precise, with correct terminology. Use only what the "
        "abstract states; do not invent numbers or claims. Keep names of models, "
        "datasets, metrics and established technical terms in their original form "
        "where that is clearer. Plain text only: no Markdown, no line breaks inside a field."
    )
