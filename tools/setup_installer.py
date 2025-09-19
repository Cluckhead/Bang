# This file creates an installer for the Simple Data Checker application.
# It sets up the desktop and Start menu shortcuts with the Bang logo.

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Main installer function."""
    print("=" * 60)
    print("Simple Data Checker - Desktop Application Installer")
    print("Bond Analytics Number Guarantor (BANG)")
    print("=" * 60)
    print()
    
    # Check if we're in the right directory
    current_dir = Path.cwd()
    if not (current_dir / "app.py").exists():
        print("Error: This installer must be run from the Simple Data Checker directory")
        print("Please navigate to the project folder and run this script again.")
        input("Press Enter to exit...")
        return
    
    print("Installing required packages...")
    try:
        # Install required packages for shortcut creation
        packages = ['winshell', 'pywin32', 'pillow']
        for package in packages:
            print(f"Installing {package}...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', package], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Warning: Failed to install {package}")
                print(f"Error: {result.stderr}")
    
    except Exception as e:
        print(f"Error installing packages: {e}")
        print("You may need to install these packages manually:")
        print("pip install winshell pywin32 pillow")
    
    print("\nCreating shortcuts...")
    try:
        # Run the shortcut creation script
        result = subprocess.run([sys.executable, 'create_shortcuts.py'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Shortcuts created successfully!")
            print(result.stdout)
        else:
            print("Error creating shortcuts:")
            print(result.stderr)
            return
            
    except Exception as e:
        print(f"Error running shortcut creator: {e}")
        return
    
    print("\n" + "=" * 60)
    print("Installation Complete!")
    print("=" * 60)
    print()
    print("You can now run Simple Data Checker by:")
    print("1. Double-clicking the 'Simple Data Checker' icon on your desktop")
    print("2. Searching for 'Simple Data Checker' in the Start menu")
    print()
    print("The application will:")
    print("- Start the Flask server automatically")
    print("- Open your default web browser to http://localhost:5000")
    print("- Display the BANG logo as the application icon")
    print()
    print("To uninstall, simply delete the shortcuts from your desktop and Start menu.")
    print()
    
    input("Press Enter to exit...")

if __name__ == "__main__":
    main() 