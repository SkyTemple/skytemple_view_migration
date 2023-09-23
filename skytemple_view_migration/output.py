from typing import Callable, Optional

import click
from click import echo


def p_info(text: str):
    echo("[i] " + text)


def p_debug(text: str):
    pass  # echo(click.style(fg="magenta", text=text))


def p_warn(text: str):
    echo(click.style(fg="yellow", text="[!] " + text))


def prompt(prompt_text: str, question_callback: Optional[Callable[[], str]]) -> str:
    o_prompt_text = prompt_text
    if question_callback is not None:
        prompt_text += " [?: context]"
    try:
        v = click.prompt(prompt_text, type=str)
    except UnicodeDecodeError:
        return prompt(o_prompt_text, question_callback)
    if v == "?" and question_callback is not None:
        echo(click.style(fg="cyan", text=question_callback()))
        return prompt(o_prompt_text, question_callback)
    return v
