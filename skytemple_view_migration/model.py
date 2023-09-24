import ast
from dataclasses import dataclass
from xml.etree import ElementTree

import ast_comments


@dataclass
class ControllerAndGlade:
    module_name: str
    controller_name: str
    controller_path: str
    glade_path: str

    def load_controller_ast(self) -> ast.AST:
        with open(self.controller_path, "r") as f:
            return ast_comments.parse(f.read())

    def load_glade_tree(self):
        parser = ElementTree.XMLParser(
            target=ElementTree.TreeBuilder(insert_comments=True)
        )
        return ElementTree.parse(self.glade_path, parser=parser)
