from abc import ABC
from typing import List, overload, Any, Callable, Tuple, Literal
from functools import reduce
from .extraction import HeadDeps, ModDeps


class Term(ABC):
    pass


class Application(Term):
    def __init__(self, functor: Term, argument: Term, decoration: str):
        self.functor = functor
        self.argument = argument
        self.decoration = decoration

    @staticmethod
    def from_arglist(functor: Term, args: List[Term], decorations: List[str]) -> 'Application':
        def from_pair(t: Term, s: Tuple[Term, str]) -> 'Application':
            return Application(t, *s)
        return reduce(from_pair, zip(args, decorations), functor)


class Abstraction(Term):
    def __init__(self, abstraction: 'Atom', body: Term, decoration: str):
        self.abstraction = abstraction
        self.body = body
        self.decoration = decoration


class Atom(Term):
    def __init__(self, idx: int):
        self.idx = idx

    @staticmethod
    @overload
    def make(idx: int, lex: Literal[True]) -> 'Lex':
        pass

    @staticmethod
    @overload
    def make(idx: int, lex: Literal[False]) -> 'Var':
        pass

    @staticmethod
    def make(idx: int, lex: bool) -> 'Atom':
        return Lex(idx) if lex else Var(idx)


class Var(Atom):
    def __init__(self, idx: int):
        super(Var, self).__init__(idx)


class Lex(Atom):
    def __init__(self, idx: int):
        super(Lex, self).__init__(idx)


def print_term(term: Term, show_decorations: bool, word_printer: Callable[[int], str]):
    def pt(_term: Term) -> str:
        return print_term(_term, show_decorations, word_printer)

    if isinstance(term, Atom):
        return word_printer(term.idx) if isinstance(term, Lex) else f'x{subscript(term.idx)}'
    elif isinstance(term, Abstraction):
        if not show_decorations or term.decoration == '→':
            return f'λ{pt(term.abstraction)}.({pt(term.body)})'
        else:
            return f'λ{pt(term.abstraction)}{superscript(term.decoration)}.({pt(term.body)})'
    elif isinstance(term, Application):
        if show_decorations and term.decoration != '→' and not isinstance(term.argument, Var):
            if term.decoration in ModDeps or term.decoration in HeadDeps:
                return f'({pt(term.functor)}{superscript(term.decoration)} {pt(term.argument)})'
            else:
                return f'({pt(term.functor)} {pt(term.argument)}{superscript(term.decoration)})'
        else:
            return f'({pt(term.functor)} {pt(term.argument)})'
    else:
        raise TypeError(f'Unexpected argument of type {type(term)}')


SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
SUP = str.maketrans('abcdefghijklmnoprstuvwxyz1', 'ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ¹')
SC = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ1→', 'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ1→')


def subscript(x: Any) -> str:
    return str(x).translate(SUB)


def superscript(x: Any) -> str:
    return str(x).translate(SUP)


def smallcaps(x: Any) -> str:
    return str(x).translate(SC)
