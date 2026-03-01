import requests
query = """[out:json][timeout:60];
area["name"="江北区"]->.target;
(
  way["building"](area.target)(29.45, 106.40, 29.68, 106.68);
  relation["building"](area.target)(29.45, 106.40, 29.68, 106.68);
);
out ids;
"""
print("Running chained filter query...")
r = requests.post('http://overpass-api.de/api/interpreter', data={'data': query})
data = r.json()
print("Buildings found:", len(data.get('elements', [])))
