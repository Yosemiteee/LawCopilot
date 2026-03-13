import urllib.request
import urllib.parse
import re

query = "İstanbul hava durumu"
url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
req = urllib.request.Request(
    url, 
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)
try:
    with urllib.request.urlopen(req, timeout=10) as response:
        html = response.read().decode('utf-8')
    
    results = []
    snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
    titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
    
    for i in range(min(len(titles), 5)):
        title = re.sub(r'<[^>]+>', '', titles[i]).strip()
        snippet = re.sub(r'<[^>]+>', '', snippets[i] if i < len(snippets) else '').strip()
        results.append(f"Baslik: {title}\nOzet: {snippet}\n")
        
    if results:
        print(f"'{query}' icin arama sonuclari:\n" + "-"*40 + "\n" + "\n".join(results))
    else:
        print(f"'{query}' icin sonuc bulunamadi.")
except Exception as e:
    print(e)
