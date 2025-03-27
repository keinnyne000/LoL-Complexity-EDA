import requests
import json

ACCESS_POINT = "https://americas.api.riotgames.com"

#----------------------------------------------------------------------------------------------------

def parse_match_data(match_data):
    return match_data['info']['participants']

def write_json_str(json, filename):
    with open(filename, 'w') as f:
        f.write(json)

def write_json_list(json_file, filename):
    with open(f"{filename}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(json_file, indent=2))

#---------------------------------------------------------------------------------------------

# gets all the parsed match data on a page of a division tier page
def get_tier_page_data(tier, division, page, api_key):
    league_data = api_get_league_page(tier, division, page, api_key)
    match_data = []
    for player in league_data['entries']:
        puuid = player['puuid']
        match_ids = api_get_matches(puuid, api_key, count = 20)
        for match_id in match_ids:
            match_data.append(parse_match_data(api_get_match_data(match_id, api_key)))
    return match_data 

def api_get_puuid(name, tag, api_key):
    url = f"{ACCESS_POINT}/riot/account/v1/accounts/by-riot-id/{name}/{tag}?api_key={api_key}"
    data = request_data(url)
    return data['puuid']

def api_get_matches(puuid, api_key, count = 100):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}&api_key={api_key}"
    data = request_data(url)
    return data

def api_get_match_data(match_id, api_key):
    url = f"{ACCESS_POINT}/lol/match/v5/matches/{match_id}?api_key={api_key}"
    data = request_data(url)
    return data

def api_get_league_page(tier, division, page, api_key):
    # tier: IRON, BRONZE, SILVER, GOLD, PLATINUM, DIAMOND, MASTER, GRANDMASTER, CHALLENGER
    # division: I, II, III, IV
    na1_access_point = 'https://na1.api.riotgames.com'
    url = f"{na1_access_point}/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={page}&api_key={api_key}"
    data = request_data(url)
    return data

def request_data(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        response.raise_for_status() 