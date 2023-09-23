import ast
from ast import ClassDef, Name, FunctionDef, Return, Assign
from typing import Optional, Tuple, List, Dict
from xml.etree.ElementTree import ElementTree

from skytemple_view_migration.collect_info import CollectInfo
from skytemple_view_migration.files import iter_controllers
from skytemple_view_migration.model import ControllerAndGlade
from skytemple_view_migration.output import p_info, p_warn, prompt, p_debug
from skytemple_view_migration.ui_xml import find_object
from skytemple_view_migration.util import assert_is, camel_case, parse_annotation


def run_phase1(skytemple_directory: str, collect_info: CollectInfo):
    p_info("Starting Phase 1.")
    for controller in iter_controllers(skytemple_directory):
        info = collect_info.entry_for_controller(controller)
        p_info(f"Processing {controller.controller_name} in {controller.module_name}.")

        controller_ast = controller.load_controller_ast()

        cls_ast, base_class, info.new_widget_name = c_class(
            controller_ast, controller.module_name
        )
        if base_class != "AbstractController":
            p_warn(f"Skipping because of not direct base class {base_class}...")
            continue
        assert cls_ast is not None

        glade_tree = controller.load_glade_tree()

        (
            func_init,
            info.module_class,
            info.item_data_type,
            info.extra_init_params,
        ) = c_params(cls_ast, controller)
        func_get_view, info.main_widget_name, info.main_widget_type = c_main_widget(
            cls_ast, glade_tree
        )

        if info.new_widget_name is None:
            info.new_widget_name = prompt(
                "Please enter the new widget class name", None
            )
        if info.module_class is None:
            info.module_class = prompt(
                "Please enter the module class", lambda: debout(func_init)
            )
        if info.main_widget_name is None:
            info.main_widget_name = prompt(
                "Please enter the main widget name", lambda: debout(func_get_view)
            )
        if info.main_widget_type is None:
            info.main_widget_type = prompt(
                "Please enter the main widget type", lambda: debout(func_get_view)
            )
        if info.item_data_type is None:
            info.item_data_type = prompt(
                "Please enter the item data type", lambda: debout(func_init)
            )

        p_debug(f"Output widget name {info.new_widget_name}.")


class BaseClassVisitor(ast.NodeVisitor):
    classes: List[Tuple[str, str, ClassDef]]

    def __init__(self):
        self.classes = []

    def visit_ClassDef(self, node: ClassDef):
        if len(node.bases) < 1:
            return
        if len(node.bases) > 1:
            p_warn(f"Skipped class {node.name} because it has multiple bases.")
        self.classes.append((node.name, assert_is(Name, node.bases[0]).id, node))


def c_class(
    tree: ast.AST, module_name: str
) -> Tuple[Optional[ClassDef], Optional[str], Optional[str]]:
    v = BaseClassVisitor()
    v.visit(tree)
    if len(v.classes) < 1:
        return None, None, None
    if len(v.classes) == 1:
        return (
            v.classes[0][2],
            v.classes[0][1],
            new_widget_name(v.classes[0][0], module_name),
        )

    filtered = [x for x in v.classes if x[0].endswith("Controller")]
    if len(filtered) < 1:
        p_warn("Found multiple classes, but none ended in *Controller.")
        return None, None, None
    if len(filtered) > 1:
        p_warn("Found multiple classes, and multiple ended in *Controller.")
    return filtered[0][2], filtered[0][1], new_widget_name(filtered[0][0], module_name)


def new_widget_name(controller_class_name: str, module_name: str) -> Optional[str]:
    if controller_class_name.endswith("Controller"):
        base = controller_class_name.replace("Controller", "")
        module_name_cc = camel_case(module_name)
        module_name_ccu = module_name_cc[0].upper() + module_name_cc[1:]
        return f"St{module_name_ccu}{base}Page"
    return None


class InitVisitor(ast.NodeVisitor):
    func: Optional[FunctionDef]
    module_class: Optional[str]
    init_data_type: Optional[str]
    extra_init_params: List[str]

    def __init__(self):
        self.func = None
        self.module_class = None
        self.init_data_type = None
        self.extra_init_params = []

    def visit_FunctionDef(self, node: FunctionDef):
        if node.name == "__init__":
            self.func = node
            has_item_data = True
            if len(node.args.args) < 3:
                if len(node.args.args) == 2 and node.args.vararg is not None:
                    has_item_data = False
                else:
                    p_warn(
                        f"Unexpected __init__ argument list length: {len(node.args.args)}"
                    )
                    return
            if node.args.args[0].arg != "self":
                p_warn(f"First parameter to __init__ was not self.")
                return
            module_param = node.args.args[1]
            self.module_class = parse_annotation(module_param.annotation)
            if has_item_data:
                item_data_param = node.args.args[2]
                self.init_data_type = parse_annotation(item_data_param.annotation)
                self.extra_init_params = [ast.unparse(x) for x in node.args.args[3:]]
            else:
                self.init_data_type = "None"


def c_params(
    tree: ClassDef, controller: ControllerAndGlade
) -> Tuple[Optional[FunctionDef], Optional[str], Optional[str], List[str]]:
    v = InitVisitor()
    v.visit(tree)
    return v.func, v.module_class, v.init_data_type, v.extra_init_params


class GetViewReturnWidgetVisitor(ast.NodeVisitor):
    func: Optional[FunctionDef]
    main_widget_name: Optional[str]
    simple_variables: Dict[str, ast.expr]

    def __init__(self):
        self.func = None
        self.main_widget_name = None
        self.simple_variables = {}

    def visit_FunctionDef(self, node: FunctionDef):
        if node.name == "get_view":
            self.func = node
            super().generic_visit(node)

    def visit_Assign(self, node: Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            self.simple_variables[var_name] = node.value

    def visit_Return(self, node: Return):
        p_debug(f"get_view return: {ast.dump(node)}")
        match node.value:
            case ast.Call(func=ast.Name(id="builder_get_assert"), args=args):
                last_arg = args[-1]
                p_debug(f"Last arg: {ast.dump(last_arg)}")
                match last_arg:
                    case ast.Constant(value=name):
                        self.main_widget_name = name
            case ast.Name(id=variable):
                if variable in self.simple_variables:
                    match self.simple_variables[variable]:
                        case ast.Call(
                            func=ast.Name(id="builder_get_assert"), args=args
                        ):
                            last_arg = args[-1]
                            p_debug(f"Last arg: {ast.dump(last_arg)}")
                            match last_arg:
                                case ast.Constant(value=name):
                                    self.main_widget_name = name


def c_main_widget(
    tree: ClassDef, glade_tree: ElementTree
) -> Tuple[Optional[FunctionDef], Optional[str], Optional[str]]:
    v = GetViewReturnWidgetVisitor()
    v.visit(tree)

    typ = None
    if v.main_widget_name is not None:
        obj = find_object(glade_tree.getroot(), v.main_widget_name)
        if obj is not None:
            typ = obj.py_class
    return v.func, v.main_widget_name, typ


def debout(func_init: Optional[FunctionDef]) -> str:
    if func_init is None:
        return "Function not found."
    return ast.unparse(func_init)
