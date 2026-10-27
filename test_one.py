from dotenv import load_dotenv
load_dotenv('.env')

import watcher
watcher.ANALYZE_IMAGES = True

# This was the webp URL you shared earlier
url = "https://i.ebayimg.com/images/g/JCoAAeSw8ZZq0zY0/s-l1600.webp"
result = watcher.analyze_measurements(url)
print("Result:", result)