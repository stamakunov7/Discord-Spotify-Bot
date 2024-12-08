import discord
from discord.ext import commands
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import json
import os
import yt_dlp as youtube_dl
import asyncio

# Load credentials
creds = json.load(open('creds.json'))

# Set environment variables for Spotipy
os.environ['SPOTIPY_CLIENT_ID'] = creds['spotify']['client_id']
os.environ['SPOTIPY_CLIENT_SECRET'] = creds['spotify']['client_secret']
os.environ['SPOTIPY_REDIRECT_URI'] = 'http://localhost:8888/callback'  # You'll need to set this in your Spotify Developer Dashboard

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='$', intents=intents)

# Dictionary to store user tokens
user_tokens = {}

# YouTube DL options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"), data=data)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    
    # Find a default channel to send the message
    default_channel = None
    for guild in bot.guilds:
        default_channel = guild.system_channel or guild.text_channels[0]
        if default_channel:
            break
    
    if default_channel:
        greeting = """
        Hello! I am Tim's Music Bot. Here's what I can do:
        
        • `$login`: Get a link to log in to your Spotify account
        • `$playlists`: View your Spotify playlists
        • `$playlist_tracks <number>`: View tracks in a specific playlist
        • `$join`: Join a voice channel
        • `$leave`: Leave the voice channel
        • `$play_track <playlist_number> <track_number>`: Play a specific track from a playlist in the voice channel
        
        To get started, use the `$login` command to connect your Spotify account!
        """
        await default_channel.send(greeting)
    else:
        print("Could not find a suitable channel to send the greeting message.")

@bot.command()
async def login(ctx):
    """Provide a login link for Spotify authentication"""
    scope = "user-library-read playlist-read-private user-read-playback-state user-modify-playback-state"
    sp_oauth = SpotifyOAuth(scope=scope)
    auth_url = sp_oauth.get_authorize_url()
    await ctx.send(f"Please click this link to log in to Spotify: {auth_url}\n"
                   f"After logging in, copy the URL you're redirected to and use the $callback command with that URL.")

@bot.command()
async def callback(ctx, *, callback_url: str = None):
    """Handle the callback from Spotify authentication"""
    if callback_url is None:
        # Try to extract the URL from the message content
        content = ctx.message.content
        words = content.split()
        if len(words) > 1:
            callback_url = ' '.join(words[1:])
        else:
            await ctx.send("Please provide the callback URL. Usage: $callback <url>")
            return

    try:
        sp_oauth = SpotifyOAuth()
        code = sp_oauth.parse_response_code(callback_url)
        token_info = sp_oauth.get_access_token(code)
        user_tokens[ctx.author.id] = token_info
        await ctx.send("Successfully logged in to Spotify!")
    except Exception as e:
        await ctx.send(f"An error occurred during authentication: {str(e)}")

@bot.command()
async def playlists(ctx):
    """Display user's Spotify playlists with enhanced error handling"""
    # Check if user is logged in
    if ctx.author.id not in user_tokens:
        await ctx.send("You need to log in first. Use the $login command.")
        return

    try:
        # Detailed token validation
        token_info = user_tokens.get(ctx.author.id)
        if not token_info:
            await ctx.send("Authentication token is missing. Please log in again.")
            return

        # Validate token structure
        if not isinstance(token_info, dict):
            await ctx.send("Invalid token format. Please log in again.")
            return

        # Check for required token keys
        if 'access_token' not in token_info:
            await ctx.send("Access token is missing. Please log in again.")
            return

        # Create Spotify client with the access token
        sp = spotipy.Spotify(auth=token_info['access_token'])

        # Add a timeout to the API call
        try:
            results = sp.current_user_playlists(limit=50)  # Add a reasonable limit
        except Exception as api_error:
            await ctx.send(f"Failed to retrieve playlists: {str(api_error)}")
            return

        # Validate API response
        if not results or 'items' not in results:
            await ctx.send("No playlists found or unexpected API response.")
            return

        # Check if playlists exist
        if not results['items']:
            await ctx.send("You don't have any Spotify playlists.")
            return

        # Generate playlist list
        playlist_list = ["Your Spotify Playlists:"]
        for i, playlist in enumerate(results['items'], 1):
            # Safely extract playlist details
            name = playlist.get('name', 'Unnamed Playlist')
            total_tracks = playlist.get('tracks', {}).get('total', 0)
            playlist_list.append(f"{i}. {name} (Tracks: {total_tracks})")
        
        # Send playlist details
        message = "\n".join(playlist_list)
        await ctx.send(message)

    except spotipy.SpotifyException as spotify_error:
        # Detailed Spotify-specific error handling
        error_message = str(spotify_error)
        
        if 'The access token expired' in error_message:
            try:
                # Attempt token refresh
                sp_oauth = SpotifyOAuth()
                token_info = sp_oauth.refresh_access_token(user_tokens[ctx.author.id].get('refresh_token'))
                
                if token_info:
                    # Update stored token
                    user_tokens[ctx.author.id] = token_info
                    await ctx.send("Your session was refreshed. Please try the command again.")
                else:
                    await ctx.send("Failed to refresh your session. Please log in again.")
            except Exception as refresh_error:
                await ctx.send(f"Token refresh failed: {str(refresh_error)}")
        else:
            await ctx.send(f"Spotify API error: {error_message}")

    except Exception as unexpected_error:
        # Catch-all for any other unexpected errors
        await ctx.send(f"An unexpected error occurred: {str(unexpected_error)}")
        # Log the full error for debugging
        import traceback
        traceback.print_exc()

@bot.command()
async def playlist_tracks(ctx, playlist_number: int):
    """Display tracks from a specific playlist"""
    if ctx.author.id not in user_tokens:
        await ctx.send("You need to log in first. Use the $login command.")
        return

    try:
        sp = spotipy.Spotify(auth=user_tokens[ctx.author.id]['access_token'])
        playlists = sp.current_user_playlists()
        
        if playlist_number < 1 or playlist_number > len(playlists['items']):
            await ctx.send("Invalid playlist number. Please use a number from your playlist list.")
            return

        selected_playlist = playlists['items'][playlist_number - 1]
        tracks = sp.playlist_tracks(selected_playlist['id'])
        
        track_list = [f"{i+1}. {track['track']['name']} - {track['track']['artists'][0]['name']}" 
                      for i, track in enumerate(tracks['items'][:20])]  # Limit to 20 tracks
        
        message = f"Tracks in '{selected_playlist['name']}':\n" + "\n".join(track_list)
        await ctx.send(message[:2000])  # Discord has a 2000 character limit

    except spotipy.SpotifyException as e:
        if 'The access token expired' in str(e):
            # Refresh the token
            sp_oauth = SpotifyOAuth()
            token_info = sp_oauth.refresh_access_token(user_tokens[ctx.author.id]['refresh_token'])
            user_tokens[ctx.author.id] = token_info
            await ctx.send("Your session expired. I've refreshed it for you. Please try the command again.")
        else:
            await ctx.send(f"An error occurred: {str(e)}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {str(e)}")

@bot.command()
async def join(ctx):
    """Joins a voice channel"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
    else:
        await ctx.send("You are not connected to a voice channel.")

@bot.command()
async def leave(ctx):
    """Leaves the voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command()
async def play_track(ctx, playlist_number: int, track_number: int):
    """Play a specific track from a playlist"""
    if ctx.author.id not in user_tokens:
        await ctx.send("You need to log in first. Use the $login command.")
        return

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You are not connected to a voice channel.")
            return

    try:
        sp = spotipy.Spotify(auth=user_tokens[ctx.author.id]['access_token'])
        
        # Get user's playlists
        playlists = sp.current_user_playlists()
        if playlist_number < 1 or playlist_number > len(playlists['items']):
            await ctx.send("Invalid playlist number.")
            return

        # Get tracks from the selected playlist
        selected_playlist = playlists['items'][playlist_number - 1]
        tracks = sp.playlist_tracks(selected_playlist['id'])
        
        if track_number < 1 or track_number > len(tracks['items']):
            await ctx.send("Invalid track number.")
            return

        # Get the selected track
        track = tracks['items'][track_number - 1]['track']
        search_query = f"{track['name']} {track['artists'][0]['name']}"

        # Search and play the track from YouTube
        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(f"ytsearch:{search_query}", loop=bot.loop, stream=True)
                ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
                await ctx.send(f"Now playing: {track['name']} by {track['artists'][0]['name']}")
            except Exception as e:
                await ctx.send(f"Error playing track: {str(e)}")
                print(f"Detailed error: {e}")  # This will print the full error to your console
                return

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        print(f"Detailed error: {e}")  # This will print the full error to your console

@bot.command()
async def stop(ctx):
    """Stop the current track"""
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Playback stopped.")
    else:
        await ctx.send("I'm not currently playing anything.")

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

def extract_audio(url):
    info = ytdl.extract_info(url, download=False)
    audio_url = info['url']
    audio_data = ytdl.urlopen(audio_url).read()
    return audio_data

bot.run(creds['discord_token'])
