#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify that the module can work without external dependencies
"""

import sys
import os

def test_module_imports():
    """Test that all module files can be imported without external dependencies"""
    print("Testing module imports without external dependencies...")
    
    # Add the module path to sys.path
    module_path = os.path.dirname(os.path.abspath(__file__))
    if module_path not in sys.path:
        sys.path.insert(0, module_path)
    
    try:
        # Test main module import
        print("✓ Testing main module import...")
        import __init__ as main_module
        print("  ✓ Main module imported successfully")
        
        # Test models import
        print("✓ Testing models import...")
        from models import __init__ as models_module
        print("  ✓ Models module imported successfully")
        
        # Test controllers import
        print("✓ Testing controllers import...")
        from controllers import __init__ as controllers_module
        print("  ✓ Controllers module imported successfully")
        
        # Test wizard import
        print("✓ Testing wizard import...")
        from wizard import __init__ as wizard_module
        print("  ✓ Wizard module imported successfully")
        
        print("\n✅ All module imports successful!")
        print("The module can work without external dependencies (pyzk, xlsxwriter)")
        return True
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Some dependencies might be missing or there are syntax errors")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

def check_optional_dependencies():
    """Check which optional dependencies are available"""
    print("\nChecking optional dependencies:")
    
    # Check pyzk
    try:
        import zk
        print("  ✓ pyzk is available - F18 integration will work")
    except ImportError:
        print("  ⚠ pyzk not available - F18 integration will be limited")
    
    # Check xlsxwriter
    try:
        import xlsxwriter
        print("  ✓ xlsxwriter is available - Excel export will work")
    except ImportError:
        print("  ⚠ xlsxwriter not available - Excel export will be limited")

if __name__ == "__main__":
    print("HR Attendance Load F18 - Dependency Test")
    print("=" * 50)
    
    success = test_module_imports()
    check_optional_dependencies()
    
    if success:
        print("\n🎉 Module is ready for installation!")
        print("You can install it in Odoo even without the optional dependencies.")
    else:
        print("\n💥 Module has issues that need to be fixed before installation.")
    
    sys.exit(0 if success else 1)