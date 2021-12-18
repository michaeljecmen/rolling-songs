import sys

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

def main():
    # TODO read sensitive fields from config.json or set environment variables
    spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

    if len(sys.argv) > 1:
        name = ' '.join(sys.argv[1:])
    else:
        name = 'Radiohead'

    results = spotify.search(q='artist:' + name, type='artist')
    items = results['artists']['items']
    if len(items) > 0:
        artist = items[0]
        print(artist['name'], artist['images'][0]['url'])

if __name__ == '__main__':
    main()