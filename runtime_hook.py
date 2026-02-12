# -*- coding: utf-8 -*-
"""
Runtime hook for PyInstaller: Azure Speech SDK DLL search path fix.
Ensures the DLL and its dependencies (VC++ Runtime) can be found.
"""
import os
import sys

if sys.platform == 'win32':
    # _MEIPASS is the _internal directory in PyInstaller 6.x
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

    # Add the azure speech DLL directory to DLL search path
    azure_dll_dir = os.path.join(base, 'azure', 'cognitiveservices', 'speech')
    if os.path.isdir(azure_dll_dir):
        os.add_dll_directory(azure_dll_dir)

    # Add the base _internal directory (for VC++ runtime DLLs)
    os.add_dll_directory(base)

    # Also add Windows system directories for VC++ runtime
    sys_dir = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    if os.path.isdir(sys_dir):
        os.add_dll_directory(sys_dir)
