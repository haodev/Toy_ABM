To run locally:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export CENSUS_API_KEY=see_below

.venv/bin/python run.py
```
Get Census API key from https://api.census.gov/data/key_signup.html
