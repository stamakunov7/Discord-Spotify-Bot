import discord
import json
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.oauth2 import SpotifyOAuth

# Load credentials
creds = json.load(open('creds.json'))

# Set environment variables for Spotipy
os.environ['SPOTIPY_CLIENT_ID'] = creds['spotify']['client_id']
os.environ['SPOTIPY_CLIENT_SECRET'] = creds['spotify']['client_secret']

# Initialize Spotipy client
spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=creds['spotify']['client_id'], client_secret=creds['spotify']['client_secret']))

# Initialize Discord client
intents = discord.Intents.default()
intents.message_content = True  # Make sure to enable message content intent if you're using Discord's newer API versions
client = discord.Client(intents=intents)

# Global variable to store current album listings
current_albums = {}

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    global current_albums

    if message.author == client.user:
        return
    
    if message.content.startswith('$help'):
        help_message = """
        **Commands to interact with the Tim's Spotify Bot:**
        `$hello` - Greet the bot.
        `$albums spotify-artist-ARTIST_ID` - List albums for the specified Spotify artist. Replace `ARTIST_ID` with the actual Spotify artist ID.
        `$tracks ALBUM_NUMBER` - Show tracks for the selected album. Replace `ALBUM_NUMBER` with the number listed next to the album name from the `$albums` command.
        """
        await message.channel.send(help_message)

    if message.content.startswith('$hello'):
        await message.channel.send('Hello!')

    if message.content.startswith('$albums'):
        try:
            _, artist_id = message.content.split('spotify-artist-')
            artist_id = artist_id.split('?')[0]  # Clean artist ID
            artist_uri = f'spotify:artist:{artist_id}'

            results = spotify.artist_albums(artist_uri, album_type='album')
            albums = results['items']
            while results['next']:
                results = spotify.next(results)
                albums.extend(results['items'])

            # Store album details with selection numbers
            current_albums = {str(index + 1): album for index, album in enumerate(albums)}

            # Generate and send the response listing albums
            response = "Here are the albums:\n" + '\n'.join([f"{index}. {album['name']}" for index, album in current_albums.items()])
            await message.channel.send(response[:2000])
        except Exception as e:
            await message.channel.send(f"An error occurred: {str(e)[:2000]}")

    if message.content.startswith('$tracks'):
        selection = message.content.split(' ')[1]  # Get the album number from the command

        if selection in current_albums:
            selected_album = current_albums[selection]
            album_id = selected_album['id']
            tracks = spotify.album_tracks(album_id)
            track_list = tracks['items']

            # Generate and send the response listing tracks
            response = f"Tracks in {selected_album['name']}:\n" + '\n'.join([f"{idx + 1}. {track['name']}" for idx, track in enumerate(track_list)])
            await message.channel.send(response[:2000])
        else:
            await message.channel.send("Please select a valid album number.")  # If the selection is invalid

client.run(creds['discord_token'])
