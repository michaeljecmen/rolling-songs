import spotipy
import pylast
import json
import datetime

def get_config():
    # IMPORTANT: config.json is the only thing that's .gitignore'd
    # don't put your details in example.json, or a file with any other name
    with open("config.json", "r") as cfile:
        config = json.load(cfile)

    # get required fields from the example file
    with open("example.json", "r") as example_conf:
        required_fields = json.load(example_conf).keys()

    error = False
    error_msg = ''
    for field in required_fields:
        if field not in config.keys():
            error = True
            error_msg += f'\"{field}\", '
    
    if error:
        print('ERROR: your config.json is missing the following required fields:')
        print('\t[ ', end='')
        error_msg = error_msg[:-2] # pop trailing comma and space
        print(error_msg, end='')
        print(' ]')
        exit(1)

    return config

def authenticate_services(config):
    # will require you to sign in via a browser the first time you launch this
    token = spotipy.util.prompt_for_user_token(
        config["SPOTIFY_USERNAME"],
        "user-library-read",
        config["SPOTIFY_CLIENT_ID"],
        config["SPOTIFY_CLIENT_SECRET"],
        config["SPOTIFY_REDIRECT_URI"]
    )
    spotify = spotipy.Spotify(auth=token)

    network = pylast.LastFMNetwork(
        api_key=config["LASTFM_API_KEY"],
        api_secret=config["LASTFM_SECRET"],
        username=config["LASTFM_USERNAME"],
        password_hash=pylast.md5(config["LASTFM_PASSWORD"])
    )
    
    return spotify, network.get_authenticated_user()

# returns list of { "name": trackname, "artists": [artists], "album": album }
# containing each song in the spotify playlist provided
def get_rolling_tracklist(config, spotify):
    spotify_username = config["SPOTIFY_USERNAME"]
    playlists = spotify.user_playlists(spotify_username)
    tracklist = []
    for playlist in playlists['items']:

        if playlist['owner']['id'] != spotify_username:
            continue

        if playlist['name'] != config["SPOTIFY_PLAYLIST"]:
            continue
        
        # found the rolling playlist
        results = spotify.playlist(playlist['id'], fields="tracks,next")
        spotify_tracks = results['tracks']
        while spotify_tracks:
            # not quite sure why the for loop is needed here
            for item in spotify_tracks['items']:
                spotify_track = item['track']
                track = {
                    "name": spotify_track['name'],
                    "artists": [ artist['name'] for artist in spotify_track['artists'] ],
                    "album": spotify_track['album']['name']
                }
                # print(track)
                tracklist.append(track)
                
            spotify_tracks = spotify.next(spotify_tracks)
        
        # can only be one rolling playlist
        break

    return tracklist

# for each track, get listens in past year by unix timestamp # TODO change this function
def append_listens(tracks, lastfm):
    for track in tracks:
        print("LISTENS FOR TRACK", track["name"])
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        listens = []
        for played_track in scrobs:
            listens.append({
                "playback_date": played_track.playback_date,
                "timestamp": played_track.timestamp
            })
        print(listens)

def main():
    config = get_config()
    spotify, lastfm = authenticate_services(config)

    tracks = get_rolling_tracklist(config, spotify)

    # TODO function which checks previous tracklist and writes a log with substitutions
    # and timestamps added, timestamps removed, and plays since added

    # TODO this should only be called at end of year
    tracks = append_listens(tracks, lastfm)

    # TODO dump data to a json file, reload and update on each execution
    # TODO end of year function which runs once and emails a file
    # TODO email me for error reporting

if __name__ == '__main__':
    main()