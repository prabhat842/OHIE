#!/usr/bin/env python3
"""
AeroGis AI Backend Launcher
Activates virtual environment and starts the Flask backend server
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    # Check if virtual environment exists
    venv_path = Path('aerogis')
    if not venv_path.exists():
        print("❌ Virtual environment 'aerogis' not found!")
        print("Please run setup first to create the virtual environment.")
        sys.exit(1)

    # Check if virtual environment is activated
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("🔧 Activating virtual environment...")

        # Get the activation script path
        if sys.platform == 'win32':
            activate_script = venv_path / 'Scripts' / 'activate.bat'
        else:
            activate_script = venv_path / 'bin' / 'activate'

        if not activate_script.exists():
            print(f"❌ Activation script not found at {activate_script}")
            sys.exit(1)

        # Start the backend server with activated environment
        cmd = f"source {activate_script} && python backend.py"
        print("🚀 Starting AeroGis AI Backend Server...")
        print("📡 Server will be available at: http://localhost:5000")
        print("🎯 WebSocket endpoint: ws://localhost:5000/socket.io/")
        print("Press Ctrl+C to stop the server")
        print()

        try:
            subprocess.run(cmd, shell=True, check=True)
        except KeyboardInterrupt:
            print("\n👋 Backend server stopped")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start backend server: {e}")
            sys.exit(1)
    else:
        print("✅ Virtual environment already activated")
        print("🚀 Starting AeroGis AI Backend Server...")

        # Import and run the backend directly
        try:
            from backend import app, socketio
            socketio.run(app, host='0.0.0.0', port=5000, debug=True)
        except ImportError as e:
            print(f"❌ Failed to import backend: {e}")
            print("Make sure all dependencies are installed in the virtual environment.")
            sys.exit(1)

if __name__ == '__main__':
    main()

