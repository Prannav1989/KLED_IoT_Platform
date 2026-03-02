import os
import sys
import subprocess
import shutil

PROJECT_NAME = "KLED_IoT_Platform"
ENTRY_FILE = "run_app.py"
PYTHON_REQUIRED = (3, 11)

def run(cmd):
    print(f">>> {cmd}")
    subprocess.check_call(cmd, shell=True)

def check_python():
    if sys.version_info[:2] != PYTHON_REQUIRED:
        print("❌ Python 3.11 is REQUIRED")
        sys.exit(1)
    print("✅ Python version OK")

def clean():
    for folder in ("build", "dist"):
        if os.path.exists(folder):
            shutil.rmtree(folder)
    for file in os.listdir("."):
        if file.endswith(".spec"):
            os.remove(file)
    print("🧹 Cleaned old builds")

def install_requirements():
    run("pip install -r requirements.txt")

def build_exe():
    cmd = (
        f'pyinstaller --clean --noconfirm '
        f'--name "{PROJECT_NAME}" '
        f'--onefile --noconsole '
        f'--icon "static\\favicon.ico" '
        f'--add-data "templates;templates" '
        f'--add-data "static;static" '
        f'--add-data "data;data" '
        f'--hidden-import engineio.async_drivers.threading '
        f'--hidden-import dotenv '
        f'--hidden-import dotenv.main '
        f'{ENTRY_FILE}'
    )
    run(cmd)

if __name__ == "__main__":
    check_python()
    install_requirements()
    clean()
    build_exe()
    print("\n🎉 EXE build completed successfully!")
