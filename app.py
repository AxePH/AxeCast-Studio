import os
import sys
import customtkinter as ctk

# Ensure project root is in Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow

def main():
    # Set default appearance
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    app = MainWindow()
    app.mainloop()

if __name__ == "__main__":
    main()
