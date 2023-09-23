import ast
from typing import Type, Any, TypeVar, Optional

T = TypeVar("T")


def assert_is(typ: Type[T], obj: Any) -> T:
    assert isinstance(obj, typ)
    return obj


def camel_case(input_string: str) -> str:
    string_with_spaces = input_string.replace("-", " ").replace("_", " ")
    title_case_string = string_with_spaces.title()
    camel_case_string = title_case_string.replace(" ", "")
    return camel_case_string[0].lower() + camel_case_string[1:]


def parse_annotation(annotation: Optional[ast.AST]):
    match annotation:
        case ast.Name(id=name):
            return name
        case ast.Constant(value=name):
            return name
        case None:
            pass
        case other:
            raise ValueError(f"Unexpected annotation type: {type(other)}")
