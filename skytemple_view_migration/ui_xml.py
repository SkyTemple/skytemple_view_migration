from dataclasses import dataclass
from typing import Optional
from xml.etree.ElementTree import Element


@dataclass
class BuilderObject:
    id: Optional[str]
    gtk_class: str
    py_class: str

    def __init__(self, id: Optional[str], gtk_class: str):
        self.id = id
        self.gtk_class = gtk_class
        if gtk_class.startswith("GtkSource"):
            self.py_class = self.gtk_class.replace("GtkSource", "GtkSource.")
        elif gtk_class.startswith("Gtk"):
            self.py_class = self.gtk_class.replace("Gtk", "Gtk.")
        else:
            raise KeyError(self.gtk_class)


def find_object(node: Element, id_name: str) -> Optional[BuilderObject]:
    if node.tag == "object" and node.attrib.get("id", None) == id_name:
        return BuilderObject(node.attrib.get("id", None), node.attrib["class"])
    for child in node:
        ret = find_object(child, id_name)
        if ret is not None:
            return ret
    return None
