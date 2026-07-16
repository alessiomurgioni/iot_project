# Mainframe - An IoT Devices Management Platform


## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```
Then start a mongo db database locally.

## Generate a device

```bash
 python -m scripts.generate_device boston-001 tok-secret-001 owner-key-001 42.36028 -71.05778
 python -m scripts.generate_device cagliari-001 tok-secret-001 owner-key-001  39.227779 9.111111
```
## Run
```bash
python app.py         # serves on 0.0.0.0:8000
```
