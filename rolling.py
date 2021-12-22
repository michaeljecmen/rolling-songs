import sys
import spotipy
import pylast
import json
import datetime
from pathlib import Path

# debug flag
debug = False

# constants
LONG_DELIMITER = '[|||]'
SHORT_DELIMITER = '[|]'
ADDED = '[+]'
REMOVED = '[-]'
DATE_FORMAT = "%Y-%m-%d"

def log(s):
    if debug:
        print(s)

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
                log(track)
                tracklist.append(track)
                
            spotify_tracks = spotify.next(spotify_tracks)
        
        # can only be one rolling playlist
        break

    return tracklist

def file_exists(filename):
    return Path(filename).exists()

# load previous tracklist from json file in config
def load_previous_tracklist(config):
    if not file_exists(config["STORAGE_FILENAME"]):
        log("first time running this program, previous tracklist not stored yet")
        return {}

    with open(config["STORAGE_FILENAME"], "r") as trackfile:
        return json.load(trackfile)

def are_tracks_same(new, old):
    # new have "name", "artists", and "album" fields
    # old have "name", "artists", "album", and "playcount" fields
    if new["name"] != old["name"]:
        return False
    if new["artists"] != old["artists"]:
        return False
    if new["album"] != old["album"]:
        return False

    return True

# linear, who cares. returns track or None if not found
def get_corresponding_track(tracklist, track):
    for new_track in tracklist:
        if are_tracks_same(new_track, track):
            return track
    return None

# for each new track, get number of plays at present and store.
# for each track which was removed from tracklist, get number of plays
# at present and deduct plays when added to get plays since added.
# returns updated tracklist, removed tracks as a pair
def update_tracklist(new_tracklist, tracklist, date, lastfm):
    # separate new tracks and kept tracks
    news = []
    kept = []
    for new_track in new_tracklist:
        existing_track = get_corresponding_track(tracklist, new_track)
        if existing_track is None:
            news.append(new_track)
        else:
            kept.append(existing_track)

    # now repeat in reverse to find removed tracks
    removed = []
    for existing_track in tracklist:
        if get_corresponding_track(new_tracklist, existing_track) is None:
            # this track must have been removed since we last checked
            removed.append(existing_track)         

    # go through olds, update playcounts and timestamp out
    for track in removed:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs) - track["playcount"]
        track["date_out"] = date

    # go through news, set playcounts and timestamp in, and append to kept
    for track in news:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs)
        track["date_in"] = date
        kept.append(track)

    # kept is now the updated current tracklist
    return kept, removed, news

# writes the track to the file provided in a consistent format
def encode_track(track):
    encoded = ""
    encoded += LONG_DELIMITER + track["name"] + LONG_DELIMITER
    for artist in track["artists"]:
        encoded += artist + SHORT_DELIMITER
    encoded += LONG_DELIMITER
    encoded += track["album"] + LONG_DELIMITER
    return encoded

# if it does not already exist, create logfile
def create_logfile(config, tracklist):
    if file_exists(config["LOG_FILENAME"]):
        return

    # create logfile and store current 25 tracks in it
    with open(config["LOG_FILENAME"], "w") as logfile:
        logfile.write("STARTING TRACKS\n")
        for track in tracklist:
            logfile.write(encode_track(track) + '\n')
        logfile.write('\n')

def append_to_log(config, removed, added, date):
    # no appending needed if no tracks were removed
    # also, skip the day altogether if there wasn't an equal exchange
    if len(removed) == 0 or len(removed) != len(added):
        return False

    # add diff to logfile
    with open(config["LOG_FILENAME"], "a") as logfile:
        logfile.write(LONG_DELIMITER + date + LONG_DELIMITER)
        for rtrack in removed:
            logfile.write(REMOVED)
            logfile.write(encode_track(rtrack))
            logfile.write(rtrack["playcount"] + LONG_DELIMITER + '\n')
        for atrack in added:
            logfile.write(ADDED)
            logfile.write(encode_track(atrack) + '\n')
        logfile.write('\n')

    return True

def write_tracklist_file(config, tracklist): # TODO have starting-songs.json and rolling log which is list of json substitutions
    with open(config["STORAGE_FILENAME"], "w") as tfile:
        if debug:
            json.dump(tracklist, tfile, indent=4, sort_keys=True)
        else:
            json.dump(tracklist, tfile)

def main():
    config = get_config()
    spotify, lastfm = authenticate_services(config)

    # get current tracks and compare to previously stored tracks
    tracklist = get_rolling_tracklist(config, spotify)

    # read previous tracklist from storage file
    previous_tracklist = load_previous_tracklist(config)

    # get diff and update playcounts for new and removed songs
    date = datetime.datetime.today().strftime(DATE_FORMAT)
    tracklist, removed, added = update_tracklist(tracklist, previous_tracklist, date, lastfm)

    # create logfile if does not exist
    create_logfile(config, tracklist)

    # finally, write the log and tracklist file to be checked next time
    append_to_log(config, removed, added, date)
    write_tracklist_file(config, tracklist)

if __name__ == '__main__':
    # debug printing on for any invocation with more than the required args
    if len(sys.argv) > 2:
        debug = True
    main()