from dotenv import load_dotenv
load_dotenv('.env')

import os
print("key present:", bool(os.environ.get('DEEPSEEK_API_KEY')))

import watcher
watcher.ANALYZE_IMAGES = True
print("ANALYZE_IMAGES:", watcher.ANALYZE_IMAGES)

url = "https://i.ebayimg.com/images/g/JCoAAeSw8ZZq0zY0/s-l1600.webp"
print("url ok:", url.startswith('https://'))

result = watcher.analyze_measurements(url)
print("result:", repr(result))