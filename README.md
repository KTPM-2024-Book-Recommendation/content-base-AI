### Move to the project directory

$cd \<project-directory\>

### Create a virtual environment

$python -m venv venv

### Activate the virtual environment

$.\venv\Scripts\activate

### Install the required packages

$pip install -r requirements.txt

### Run the project

$python relativeAPI.py

### Open new Terminal & Port mapping by ngrok with flask port: 5000

$ngrok http 5000
