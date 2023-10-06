import ast
import os.path
from _ast import Module, ClassDef, FunctionDef, Call
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Dict, Tuple, Optional, Any, List
from xml.etree.ElementTree import ElementTree, Element

import ast_comments

from skytemple_view_migration import CollectInfo, p_info
from skytemple_view_migration.collect_info import CollectInfoEntry
from skytemple_view_migration.model import ControllerAndGlade
from skytemple_view_migration.output import p_warn
from skytemple_view_migration.ui_xml import BuilderObject
from skytemple_view_migration.util import assert_not_none, assert_is


def run_phase2(skytemple_directory: str, collect_info: CollectInfo):
    p_info("Starting Phase 2.")
    sd_abs = os.path.abspath(skytemple_directory)
    for entry in collect_info.entries.values():
        if entry.module_class is None or entry.new_widget_name is None:
            continue
        p_info(f"Processing {entry.controller_name} in {entry.module_name}.")

        widget_out_dir = os.path.join(
            sd_abs, "skytemple", "module", entry.module_name, "widget"
        )
        ui_out_dir = os.path.join(
            sd_abs, "skytemple", "data", "widget", entry.module_name
        )
        os.makedirs(widget_out_dir, exist_ok=True)
        Path(widget_out_dir).joinpath("__init__.py").touch()
        os.makedirs(ui_out_dir, exist_ok=True)

        widget_path = os.path.join(widget_out_dir, f"{entry.controller_name}.py")
        ui_path = os.path.join(ui_out_dir, f"{entry.controller_name}.ui")

        controller = ControllerAndGlade(
            entry.module_name,
            entry.controller_name,
            entry.controller_path,
            entry.glade_path,
        )
        controller_ast = controller.load_controller_ast()
        ui_tree = controller.load_glade_tree()
        widget_ast = transform_widget_ast(controller_ast, ui_tree, entry)

        with open(widget_path, "w") as f:
            # We remove all type: ignore's because they may be misplaced now.
            body = ast_comments.unparse(widget_ast).replace("# type: ignore", "")
            if "self.builder" in body or "self._builder" in body:
                p_warn("Still contains builder references.")
            f.write(body)

        transform_ui_tree(ui_tree, entry)

        with open(ui_path, "wb") as f:
            ui_tree.write(f, encoding="utf-8", xml_declaration=True)


@dataclass
class ActionsControllerToWidget:
    """
    - mod: Adds __future__ annotations, removes AbstractController, builder_get_assert imports
    - cls: Add Gtk.Template decorator to class
    - cls: Change class name, change base
    - cls: Add __gtype_name__ to class
    - cls: Adds module and item data attributes to class
    - cls: Adds child widgets to class
    - cls: Merges __init__ and get_view into __init__
    - fun: Adds callbacks to signal handlers
    - fun: Add super call to __init__
    - fun: Remove self.builder = from __init__
    - fun: Removes return from __init__
    - cll: Replaces all builder_get_assert([self.]builder, <TY>, <NAME>) with self.<NAME>
    """

    mod_add_imports: bool = field(default=False)
    cls_add_gtk_template: bool = field(default=False)
    cls_change_class: bool = field(default=False)
    cls_add_gtype_name: bool = field(default=False)
    cls_add_mod_itm_data: bool = field(default=False)
    cls_add_child_wdgs: bool = field(default=False)
    cls_merge_init_get_view: bool = field(default=False)
    fun_add_callbacks: bool = field(default=False)
    fun_add_super: bool = field(default=False)
    fun_remove_builder: bool = field(default=False)
    fun_remove_init_ret: bool = field(default=False)
    cll_replace_builder: bool = field(default=False)

    def assert_done(self):
        for k, v in self.__dict__.items():
            if not v:
                raise AssertionError(f"Did not {k}")


class ControllerToWidgetTransformer(ast.NodeTransformer):
    actions_done: ActionsControllerToWidget
    info: CollectInfoEntry
    widgets: Dict[str, str]
    signal_handlers: Set[str]
    widget_renames: Dict[str, str]

    def __init__(
        self,
        info: CollectInfoEntry,
        widgets: Dict[str, str],
        signal_handlers: Set[str],
    ):
        self.actions_done = ActionsControllerToWidget()
        self.info = info
        self.widgets = widgets
        self.signal_handlers = signal_handlers
        self.widget_renames = {}

    def visit_Module(self, node: Module) -> ast.AST:
        # Imports:
        new_body: List[ast.stmt] = []
        inserted_from_future = False
        has_os_import = False
        has_data_dir_import = False
        has_typing_cast = False
        for i in range(0, len(node.body)):
            append_this = True
            this_n = node.body[i]
            if isinstance(this_n, ast.Import):
                for n in this_n.names:
                    if n.name == "os":
                        has_os_import = True
            elif isinstance(this_n, ast.ImportFrom):
                if this_n.module == "skytemple.core.module_controller":
                    this_n.names = [
                        x for x in this_n.names if x.name != "AbstractController"
                    ]
                    if len(this_n.names) < 1:
                        append_this = (
                            False  # skip this import from statement, it is now empty.
                        )
                elif this_n.module == "skytemple.core.ui_utils":
                    this_n.names = [
                        x for x in this_n.names if x.name != "builder_get_assert"
                    ]
                    l_has_data_dir = False
                    for n in this_n.names:
                        if n.name == "data_dir":
                            l_has_data_dir = True
                    if not l_has_data_dir:
                        this_n.names.append(ast.alias(name="data_dir"))
                    has_data_dir_import = True
                    if len(this_n.names) < 1:
                        append_this = (
                            False  # skip this import from statement, it is now empty.
                        )
                elif this_n.module == "typing":
                    l_has_cast = False
                    for n in this_n.names:
                        if n.name == "cast":
                            l_has_cast = True
                    if not l_has_cast:
                        this_n.names.append(ast.alias(name="cast"))
                    has_typing_cast = True

            if append_this:
                new_body.append(this_n)

            next_i = i + 1
            if next_i < len(node.body):
                next_n = node.body[next_i]
                if not inserted_from_future and (
                    isinstance(next_n, ast.Import) or isinstance(next_n, ast.ImportFrom)
                ):
                    inserted_from_future = True
                    match next_n:
                        case ast.ImportFrom(module="__future__"):
                            # already exists, probably.
                            assert (
                                len(
                                    [x for x in next_n.names if x.name == "annotations"]
                                )
                                > 0
                            )
                        case _:
                            new_body.append(stmt("from __future__ import annotations"))
                if isinstance(next_n, ast.ClassDef):
                    if not has_data_dir_import:
                        new_body.append(
                            stmt(
                                "from skytemple.core.ui_utils import data_dir",
                            )
                        )

                    if not has_os_import:
                        new_body.append(stmt("import os"))

                    if not has_typing_cast:
                        new_body.append(
                            stmt(
                                "from typing import cast",
                            )
                        )

        node.body = new_body
        self.actions_done.mod_add_imports = True

        ret = self.generic_visit(node)
        self.actions_done.assert_done()
        return ret

    def visit_ClassDef(self, node: ClassDef) -> ast.AST:
        if node.name != self.info.controller_class_name:
            return node
        # Add Gtk.Template decorator to class
        node.decorator_list.append(
            expr(
                f'Gtk.Template(filename=os.path.join(data_dir(), "widget", "{self.info.module_name}", "{self.info.controller_name}.ui"))',
            )
        )
        self.actions_done.cls_add_gtk_template = True

        # Change class name, change base
        node.name = assert_not_none(self.info.new_widget_name)
        node.bases = [expr(assert_not_none(self.info.main_widget_type))]
        self.actions_done.cls_change_class = True

        # Add __gtype_name__ to class
        node.body.insert(0, stmt(f'__gtype_name__ = "{self.info.new_widget_name}"'))
        self.actions_done.cls_add_gtype_name = True

        # Adds module and item data attributes to class
        node.body.insert(1, stmt(f"module: {self.info.module_class}"))
        node.body.insert(
            2, stmt(f"item_data: {assert_not_none(self.info.item_data_type)}")
        )
        self.actions_done.cls_add_mod_itm_data = True

        self.widget_renames = {}
        # Adds child widgets to class
        for name, clazz in reversed(self.widgets.items()):
            # If we get a syntax error, then the widget has a reserved name. Rename it.
            try:
                node.body.insert(
                    3, stmt(f"{name}: {clazz} = cast({clazz}, Gtk.Template.Child())")
                )
            except SyntaxError:
                node.body.insert(
                    3,
                    stmt(
                        f'{name}_widget: {clazz} = cast({clazz}, Gtk.Template.Child("{name}"))'
                    ),
                )
                self.widget_renames[name] = f"{name}_widget"
        self.actions_done.cls_add_child_wdgs = True

        # Merges __init__ and get_view into __init__
        f_init: Optional[FunctionDef] = None
        f_get_view: Optional[FunctionDef] = None
        new_body = []
        for child in node.body:
            if isinstance(child, FunctionDef):
                if child.name == "__init__":
                    f_init = child
                elif child.name == "get_view":
                    f_get_view = child
                    continue  # continue so we remove it.
            new_body.append(child)
        assert f_init is not None and f_get_view is not None
        f_init.body.extend(f_get_view.body)
        node.body = new_body
        self.actions_done.cls_merge_init_get_view = True

        return self.generic_visit(node)

    def visit_FunctionDef(self, node: FunctionDef) -> ast.AST:
        # Adds callbacks to signal handlers
        if node.name in self.signal_handlers:
            node.decorator_list.append(
                expr(
                    "Gtk.Template.Callback()",
                )
            )
        self.actions_done.fun_add_callbacks = True

        if node.name == "__init__":
            # Add super call to __init__
            node.body.insert(0, stmt("super().__init__()"))
            node.body.insert(1, stmt(f"self.module = {node.args.args[1].arg}"))
            if len(node.args.args) > 2:
                node.body.insert(2, stmt(f"self.item_data = {node.args.args[2].arg}"))
            else:
                node.body.insert(2, stmt(f"self.item_data = None"))
            self.actions_done.fun_add_super = True

            # Removes return from __init__
            last_child = node.body[-1]
            if isinstance(last_child, ast.Return):
                node.body.remove(last_child)
            self.actions_done.fun_remove_init_ret = True

        return self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> Optional[ast.AST]:
        match node.test:
            case ast.Attribute(value=ast.Name(id="self"), attr="builder"):
                return None
            case ast.Attribute(value=ast.Name(id="self"), attr="_builder"):
                return None
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Optional[ast.AST]:
        # Remove self.builder =
        self.actions_done.fun_remove_builder = True
        if len(node.targets) == 1:
            match node.targets[0]:
                case ast.Attribute(value=ast.Name(id="self"), attr="builder"):
                    return None
                case ast.Attribute(value=ast.Name(id="self"), attr="_builder"):
                    return None
        match node.value:
            case ast.Call(
                func=ast.Attribute(value=ast.Name(id="self"), attr="_get_builder")
            ):
                return None
        return self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Optional[ast.AST]:
        # Remove self.builder =
        self.actions_done.fun_remove_builder = True
        match node.target:
            case ast.Attribute(value=ast.Name(id="self"), attr="builder"):
                return None
            case ast.Attribute(value=ast.Name(id="self"), attr="_builder"):
                return None
        match node.value:
            case ast.Call(
                func=ast.Attribute(value=ast.Name(id="self"), attr="_get_builder")
            ):
                return None
        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> Optional[ast.AST]:
        nnode = self.generic_visit(node)
        # This can happen if a call is removed below.
        if not hasattr(nnode, "value"):
            return None
        return nnode

    def visit_Call(self, node: Call) -> Optional[ast.AST]:
        new_node: ast.AST = node
        match node.func:
            # Remove connect signals.
            case ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="self"), attr="builder"),
                attr="connect_signals",
            ):
                return None
            case ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="self"), attr="_builder"),
                attr="connect_signals",
            ):
                return None
            # Replaces all builder_get_assert([self.]builder, <TY>, <NAME>) with self.<NAME>
            case ast.Name(id="builder_get_assert"):
                match node.args[2]:
                    case ast.Constant(value=widget_name):
                        if widget_name in self.widget_renames:
                            widget_name = self.widget_renames[widget_name]
                        new_node = expr(f"self.{widget_name}")
                    case ast.JoinedStr(values):
                        if len(values) == 1:
                            assert isinstance(values[0], ast.Constant)
                            widget_name = values[0].value
                            if widget_name in self.widget_renames:
                                widget_name = self.widget_renames[widget_name]
                            new_node = expr(f"self.{widget_name}")
                        else:
                            new_node = expr(
                                f"getattr(self, {ast.unparse(node.args[2])})"
                            )
                    case ast.Name(id=var_name):
                        new_node = expr(f"getattr(self, {var_name})")
                    case other:
                        raise AssertionError(other)
        self.actions_done.cll_replace_builder = True

        return self.generic_visit(new_node)


def collect_widgets(
    node: Element,
    accu_wdgs: Optional[Dict[str, str]] = None,
    accu_sigh: Optional[Set[str]] = None,
) -> Tuple[Dict[str, str], Set[str]]:
    if accu_wdgs is None:
        accu_wdgs = {}
    if accu_sigh is None:
        accu_sigh = set()

    if node.tag == "object" and "id" in node.attrib and "class" in node.attrib:
        accu_wdgs[node.attrib["id"]] = BuilderObject(
            None, node.attrib["class"]
        ).py_class
    if node.tag == "signal" and "handler" in node.attrib:
        accu_sigh.add(node.attrib["handler"])
    for child in node:
        collect_widgets(child, accu_wdgs, accu_sigh)
    return accu_wdgs, accu_sigh


def transform_widget_ast(
    controller_ast: ast.AST, glade_tree: ElementTree, info: CollectInfoEntry
) -> ast.AST:
    widgets, signal_handlers = collect_widgets(glade_tree.getroot())
    del widgets[info.main_widget_name]
    v = ControllerToWidgetTransformer(info, widgets, signal_handlers)
    return v.visit(controller_ast)


def transform_ui_tree(glade_tree: ElementTree, info: CollectInfoEntry):
    for node in glade_tree.getroot():
        # We search only on the top level, since it really has to be there.
        if (
            node.tag == "object"
            and node.attrib.get("id", None) == info.main_widget_name
        ):
            node.tag = "template"
            del node.attrib["id"]
            node.attrib["class"] = assert_not_none(info.new_widget_name)
            node.attrib["parent"] = assert_not_none(info.main_widget_type).replace(
                ".", ""
            )
            return
    raise ValueError("Did not find main widget to convert to template.")


def stmt(stmt: str) -> ast.stmt:
    return ast.parse(
        stmt,
        mode="single",
    ).body[0]


def expr(expr: str) -> ast.expr:
    return assert_is(ast.Expr, stmt(expr)).value
