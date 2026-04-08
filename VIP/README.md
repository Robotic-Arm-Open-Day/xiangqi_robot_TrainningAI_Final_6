# Xiangqi Robot Project - VIP Setup Guide

This guide explains how to set up the Python virtual environment and run the main `VIP` codebase. 

> **Important:** All project files outside of the `VIP` directory are considered legacy code. All current active development and execution should happen inside the `VIP` folder.

## Prerequisites
* **Python 3.11.9**: It is **critical** to use Python 3.11.x. Newer versions like Python 3.14 currently lack pre-compiled binaries for complex dependencies like `torch`, `opencv-python`, and `ultralytics`. Building these from source on newer Python versions will result in compilation errors. Additionally, the C-extension `robot_sdk_core` relies on the stable C-API of Python 3.11.

## 1. Setup the Virtual Environment

Open PowerShell in the root directory of the project (`...\xiangqi_robot_TrainningAI_Final_6`) and create a new virtual environment.

```powershell
# Verify that your global python is version 3.11.9
python --version

# Create the virtual environment named 'venv'
python -m venv venv
```

*(Note: If your default `python` command points to a different version, provide the absolute path to your Python 3.11.9 executable instead, e.g., `C:\Path\To\Python311\python.exe -m venv venv`)*

## 2. Install Project Requirements

Next, install all required dependencies listed in the root `requirements.txt` into the newly created virtual environment:

```powershell
# Install dependencies using the venv's pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Running the Project

The core application is initialized via `main_VIP.py` located inside the `VIP` folder.

To run the project, navigate into the `VIP` directory and execute the script using the virtual environment's Python executable:

```powershell
# Move into the VIP directory
cd VIP

# Run the project using the virtual environment
..\venv\Scripts\python.exe main_VIP.py
```

Alternatively, if you activate the virtual environment in your session first:
```powershell
# Activate from the project root
.\venv\Scripts\activate

# Move to VIP and run
cd VIP
python main_VIP.py
```

## Troubleshooting

* **`ModuleNotFoundError: No module named '...'`**: This means you are likely running the global `py` or `python` command instead of the Python executable inside your `venv`. Double-check that you are using `..\venv\Scripts\python.exe`.
* **PyTorch or OpenCV failing to install**: You accidentally created the virtual environment using a Python version newer than 3.11 (e.g., Python 3.14). Delete the `venv` folder and recreate it explicitly using Python 3.11.
