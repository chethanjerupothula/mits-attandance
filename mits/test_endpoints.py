import requests
for path in ['/', '/status', '/results']:
    try:
        r = requests.get('http://127.0.0.1:8000' + path, timeout=5)
        print(path, r.status_code)
        print(r.text[:300])
    except Exception as e:
        print(path, 'ERROR', e)
