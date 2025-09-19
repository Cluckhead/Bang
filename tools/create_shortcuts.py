# This file creates desktop and Start menu shortcuts for the Simple Data Checker application.
# It uses the Bang.jpg logo as the icon and creates shortcuts that run the batch file.

import os
import sys
import shutil
from pathlib import Path
import winshell
from win32com.client import Dispatch

def create_shortcuts():
    """Create desktop and Start menu shortcuts for the Simple Data Checker application."""
    
    # Get the current directory (where the script is located)
    app_dir = Path(__file__).parent.absolute()
    
    # Paths
    batch_file = app_dir / "run_app.bat"
    icon_file = app_dir / "static" / "images" / "Bang.jpg"
    
    # Check if required files exist
    if not batch_file.exists():
        print(f"Error: Batch file not found at {batch_file}")
        return False
    
    if not icon_file.exists():
        print(f"Error: Icon file not found at {icon_file}")
        return False
    
    # Convert JPG to ICO for better Windows compatibility
    ico_file = app_dir / "Bang.ico"
    try:
        from PIL import Image
        
        # Open the JPG and convert to ICO
        img = Image.open(icon_file)
        # Resize to standard icon sizes
        img = img.resize((256, 256), Image.Resampling.LANCZOS)
        img.save(ico_file, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
        print(f"Created ICO file: {ico_file}")
        icon_to_use = str(ico_file)
    except ImportError:
        print("PIL/Pillow not available, using JPG as icon (may not display properly)")
        icon_to_use = str(icon_file)
    except Exception as e:
        print(f"Error converting icon: {e}, using JPG as fallback")
        icon_to_use = str(icon_file)
    
    # Create desktop shortcut
    try:
        desktop = winshell.desktop()
        desktop_shortcut = os.path.join(desktop, "Simple Data Checker.lnk")
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(desktop_shortcut)
        shortcut.Targetpath = str(batch_file)
        shortcut.WorkingDirectory = str(app_dir)
        shortcut.IconLocation = icon_to_use
        shortcut.Description = "Simple Data Checker - Bond Analytics Number Guarantor"
        shortcut.save()
        
        print(f"Desktop shortcut created: {desktop_shortcut}")
        
    except Exception as e:
        print(f"Error creating desktop shortcut: {e}")
        return False
    
    # Create Start menu shortcut
    try:
        start_menu = winshell.start_menu()
        start_menu_folder = os.path.join(start_menu, "Simple Data Checker")
        os.makedirs(start_menu_folder, exist_ok=True)
        
        start_menu_shortcut = os.path.join(start_menu_folder, "Simple Data Checker.lnk")
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(start_menu_shortcut)
        shortcut.Targetpath = str(batch_file)
        shortcut.WorkingDirectory = str(app_dir)
        shortcut.IconLocation = icon_to_use
        shortcut.Description = "Simple Data Checker - Bond Analytics Number Guarantor"
        shortcut.save()
        
        print(f"Start menu shortcut created: {start_menu_shortcut}")
        
    except Exception as e:
        print(f"Error creating Start menu shortcut: {e}")
        return False
    
    print("\nShortcuts created successfully!")
    print("You can now run Simple Data Checker from:")
    print("- Desktop shortcut")
    print("- Start menu -> Simple Data Checker")
    print("\nThe application will open in your default web browser at http://localhost:5000")
    
    return True

def install_requirements():
    """Install required packages for shortcut creation."""
    required_packages = ['winshell', 'pywin32', 'pillow']
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            print(f"Installing {package}...")
            os.system(f"pip install {package}")

if __name__ == "__main__":
    print("Simple Data Checker - Shortcut Creator")
    print("=" * 40)
    
    # Install required packages
    print("Checking required packages...")
    install_requirements()
    
    # Create shortcuts
    if create_shortcuts():
        print("\nSetup completed successfully!")
        input("Press Enter to exit...")
    else:
        print("\nSetup failed. Please check the error messages above.")
        input("Press Enter to exit...") 