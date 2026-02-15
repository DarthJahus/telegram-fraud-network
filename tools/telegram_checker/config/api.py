API_ID = int(open('.secret/api_id', 'r', encoding='utf-8').read().strip())
API_HASH = open('.secret/api_hash', 'r', encoding='utf-8').read().strip()
SLEEP_BETWEEN_CHECKS = 20  # seconds between each check
