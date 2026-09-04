"""
ramus_rsf_tool -- a reader/writer/editor for Ramus (.rsf) IDEF0/DFD model
files, including a full Qt GUI.

Package layout:
    rsf_core.py   -- low-level container format (zip + generic XML tables)
    rsf_model.py  -- semantic EAV layer (qualifiers/elements/attributes)
    rsf_cli.py    -- command-line inspector, kept for scripting/automation
    gui/          -- the desktop GUI application (PyQt6)
"""

__version__ = "1.0.0"
