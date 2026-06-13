"""GridFinity slicer: cut exact 42 mm units out of a mesh and weld it back together."""

from .core import GRID, GridInfo, cut, export_mesh, inspect, load_mesh

__all__ = ["GRID", "GridInfo", "cut", "export_mesh", "inspect", "load_mesh"]
