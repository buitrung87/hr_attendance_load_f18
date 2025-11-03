#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to check Python syntax of all module files
"""

import os
import py_compile
import sys

def test_python_files():
    """Test Python syntax of all .py files in the module"""
    print("Testing Python syntax for all module files...")
    
    module_path = os.path.dirname(os.path.abspath(__file__))
    errors = []
    
    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(module_path):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    print(f"Found {len(python_files)} Python files to test:")
    
    for py_file in python_files:
        rel_path = os.path.relpath(py_file, module_path)
        try:
            py_compile.compile(py_file, doraise=True)
            print(f"  ✓ {rel_path}")
        except py_compile.PyCompileError as e:
            print(f"  ❌ {rel_path}: {e}")
            errors.append((rel_path, str(e)))
        except Exception as e:
            print(f"  ❌ {rel_path}: {e}")
            errors.append((rel_path, str(e)))
    
    if errors:
        print(f"\n❌ Found {len(errors)} syntax errors:")
        for file, error in errors:
            print(f"  - {file}: {error}")
        return False
    else:
        print(f"\n✅ All {len(python_files)} Python files have valid syntax!")
        return True

if __name__ == "__main__":
    print("HR Attendance Load F18 - Syntax Test")
    print("=" * 50)
    
    success = test_python_files()
    
    if success:
        print("\n🎉 Module syntax is valid!")
        print("Ready for installation in Odoo.")
    else:
        print("\n💥 Module has syntax errors that need to be fixed.")
    
    sys.exit(0 if success else 1)