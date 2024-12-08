import os
import json
import logging
import asyncio
from typing import Dict, Optional

import discord
from discord.ext import commands, tasks
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import yt_dlp as youtube_dl
from dotenv import load_dotenv

# Configure logging with more detailed configuration
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SpotifyMusicBot')

# Load environment variables
load_dotenv()

# Configuration Class
class BotConfig:
    def __init__(self, creds_file='creds.json'):
        try:
            with open(creds_file, 'r') as f:
                self.creds = json.load(f)
        except FileNotFoundError:
            logger.error(f"Credentials file {creds_file} not found!")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in credentials file {creds_file}")
            raise

        # Spotify configuration
        self.spotify_client_id = self.creds['spotify']['client_id']
        self.spotify_client_secret = self.creds['spotify']['client_secret']
        self.spotify_redirect_uri = self.creds['spotify']['redirect_uri']
        
        # Discord token
        self.discord_token = self.creds['discord_token']

        # Spotify OAuth scopes
        self.spotify_scopes = [
            'user-library-read', 
            'playlist-read-private', 
            'user-read-playback-state'
        ]

# Token Management
class TokenManager:
    def __init__(self):
        self.tokens = {}

    def add_token(self, user_id: int, token_info: dict):
        logger.debug(f"Adding token for user {user_id}")
        self.tokens[str(user_id)] = token_info

    def get_token(self, user_id: int) -> Optional[dict]:
        token = self.tokens.get(str(user_id))
        return token

# YouTube Audio Extraction
class YouTubeAudioExtractor:
    def __init__(self):
        self.ytdl_format_options = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'nooverwrites': True,
            'no_color': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
        self.ytdl = youtube_dl.YoutubeDL(self.ytdl_format_options)

    async def extract_audio(self, search_query: str, loop=None):
        loop = loop or asyncio.get_event_loop()
        try:
            # Use YouTube search with the query
            info = await loop.run_in_executor(
                None, 
                lambda: self.ytdl.extract_info(f"ytsearch:{search_query}", download=False)
            )
            
            # Get the first search result
            if 'entries' in info:
                first_result = info['entries'][0]
            else:
                first_result = info

            return first_result['url']
        except Exception as e:
            logger.error(f"YouTube audio extraction error: {e}")
            return None

# Initialize global instances
config = BotConfig()
token_manager = TokenManager()
youtube_extractor = YouTubeAudioExtractor()

# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='$', intents=intents)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="Spotify Playlists"
        )
    )

@bot.command()
async def login(ctx):
    """Initiate Spotify login process"""
    try:
        sp_oauth = SpotifyOAuth(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            redirect_uri=config.spotify_redirect_uri,
            scope=config.spotify_scopes
        )
        auth_url = sp_oauth.get_authorize_url()
        await ctx.send(
            "Please click this link to log in to Spotify:\n"
            f"{auth_url}\n\n"
            "After logging in, copy the ENTIRE URL you are redirected to and use the $callback command."
        )
    except Exception as e:
        logger.error(f"Login process error: {e}")
        await ctx.send("An error occurred during the login process.")

@bot.command()
async def callback(ctx, *, callback_url: str = None):
    try:
        sp_oauth = SpotifyOAuth(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            redirect_uri=config.spotify_redirect_uri,
            scope=config.spotify_scopes
        )
        
        code = sp_oauth.parse_response_code(callback_url)
        
        # Ensure as_dict=True to get full token information
        token_info = sp_oauth.get_access_token(code, as_dict=True)
        
        if not token_info:
            await ctx.send("Authentication failed. Please try again.")
            return

        token_manager.add_token(ctx.author.id, token_info)
        await ctx.send("Successfully authenticated with Spotify!")
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        await ctx.send(f"Authentication failed: {e}")

@bot.command()
async def playlists(ctx):
    """Display user's Spotify playlists with enhanced error handling"""
    try:
        # 1. Token validation with extensive logging
        token_info = token_manager.get_token(ctx.author.id)
        logger.critical(f"Raw token info for user {ctx.author.id}: {token_info}")
        
        if not token_info:
            logger.warning(f"No token found for user {ctx.author.id}")
            await ctx.send("Please log in first using the $login command.")
            return

        # Validate token structure
        if not isinstance(token_info, dict):
            logger.error(f"Invalid token type: {type(token_info)}")
            await ctx.send("Invalid token. Please log in again using $login")
            return

        # Ensure token has required keys
        required_keys = ['access_token', 'refresh_token', 'expires_at']
        missing_keys = [key for key in required_keys if key not in token_info]
        if missing_keys:
            logger.error(f"Token missing keys: {missing_keys}")
            await ctx.send(f"Incomplete token. Missing: {missing_keys}. Please log in again.")
            return

        # 2. Create Spotify OAuth handler
        sp_oauth = SpotifyOAuth(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            redirect_uri=config.spotify_redirect_uri,
            scope=config.spotify_scopes
        )

        # 3. Check and refresh token if expired
        try:
            # Explicitly check if token is expired
            if sp_oauth.is_token_expired(token_info):
                logger.info("Token expired. Attempting to refresh.")
                # Attempt to refresh token
                new_token = sp_oauth.refresh_access_token(token_info['refresh_token'])
                
                if not new_token:
                    logger.error("Token refresh failed")
                    await ctx.send("Failed to refresh token. Please log in again using $login")
                    return
                
                # Update token in token manager
                token_manager.add_token(ctx.author.id, new_token)
                token_info = new_token
                logger.info("Token successfully refreshed")
        except Exception as refresh_error:
            logger.error(f"Token refresh error: {refresh_error}", exc_info=True)
            await ctx.send("Error refreshing token. Please log in again.")
            return

        # 4. Create Spotify client
        try:
            sp = spotipy.Spotify(auth=token_info['access_token'])
        except Exception as client_error:
            logger.error(f"Spotify client creation error: {client_error}")
            await ctx.send("Could not create Spotify client. Please try again.")
            return

        # 5. Verify user and get playlists
        try:
            # Verify current user to validate token
            current_user = sp.current_user()
            logger.info(f"Current user verified: {current_user['display_name']}")

            # Fetch playlists
            results = sp.current_user_playlists(limit=50)
            logger.debug(f"Playlists query results: {results}")
        except spotipy.SpotifyException as query_error:
            logger.error(f"Spotify API query error: {query_error}", exc_info=True)
            await ctx.send("Error retrieving playlists. Please try logging in again.")
            return

        # 6. Process and display playlists
        try:
            playlists = results.get('items', [])
            if not playlists:
                await ctx.send("You don't have any Spotify playlists.")
                return

            # Format response with null checks
            response = ["Your Spotify Playlists:"]
            for i, playlist in enumerate(playlists, 1):
                if playlist is None:
                    continue
                    
                name = playlist.get('name', 'Unknown')
                tracks_info = playlist.get('tracks', {})
                if isinstance(tracks_info, dict):
                    total_tracks = tracks_info.get('total', 0)
                else:
                    total_tracks = 0
                    
                response.append(f"{i}. {name} ({total_tracks} tracks)")

            await ctx.send("\n".join(response))

        except Exception as e:
            logger.error(f"Unexpected playlist retrieval error: {str(e)}", exc_info=True)
            await ctx.send("An error occurred while processing playlists.")

    except Exception as e:
        logger.error(f"Unexpected playlist retrieval error: {e}", exc_info=True)
        await ctx.send("An unexpected error occurred. Please try again.")

# Rest of the commands remain the same as in the previous implementation
@bot.command()
async def playlist_tracks(ctx, playlist_number: int):
    """Show tracks in a specific Spotify playlist"""
    token_info = token_manager.get_token(ctx.author.id)
    if not token_info:
        await ctx.send("You need to log in first. Use $login command.")
        return

    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        playlists = sp.current_user_playlists()
        
        if playlist_number < 1 or playlist_number > len(playlists['items']):
            await ctx.send("Invalid playlist number.")
            return

        selected_playlist = playlists['items'][playlist_number - 1]
        tracks = sp.playlist_tracks(selected_playlist['id'])
        
        track_list = [
            f"{i+1}. {track['track']['name']} - {track['track']['artists'][0]['name']}" 
            for i, track in enumerate(tracks['items'][:20])
        ]
        
        await ctx.send(f"Tracks in '{selected_playlist['name']}':\n" + "\n".join(track_list))
    except Exception as e:
        logger.error(f"Playlist tracks error: {e}")
        await ctx.send(f"Error retrieving tracks: {e}")

# Remaining commands (play_track, join, leave) stay the same as in the previous implementation

@bot.command()
async def play_track(ctx, playlist_number: int, track_number: int):
    """Play a specific track from a Spotify playlist"""
    # Check if user is in a voice channel
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to play music.")
        return

    # Ensure bot is in the voice channel
    voice_channel = ctx.author.voice.channel
    if not ctx.voice_client:
        await voice_channel.connect()

    token_info = token_manager.get_token(ctx.author.id)
    if not token_info:
        await ctx.send("You need to log in first. Use $login command.")
        return

    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Get playlists and validate playlist number
        playlists = sp.current_user_playlists()
        if playlist_number < 1 or playlist_number > len(playlists['items']):
            await ctx.send("Invalid playlist number.")
            return

        # Get tracks from selected playlist
        selected_playlist = playlists['items'][playlist_number - 1]
        tracks = sp.playlist_tracks(selected_playlist['id'])
        
        if track_number < 1 or track_number > len(tracks['items']):
            await ctx.send("Invalid track number.")
            return

        # Get the selected track
        track = tracks['items'][track_number - 1]['track']
        search_query = f"{track['name']} {track['artists'][0]['name']}"

        # Extract audio from YouTube
        audio_url = await youtube_extractor.extract_audio(search_query)
        
        if not audio_url:
            await ctx.send("Could not find audio for the track.")
            return

        # Play the audio
        def after_playing(error):
            if error:
                logger.error(f"Playback error: {error}")
            asyncio.run_coroutine_threadsafe(ctx.voice_client.disconnect(), bot.loop)

        ctx.voice_client.play(
            discord.FFmpegPCMAudio(audio_url), 
            after=after_playing
        )
        
        await ctx.send(f"Now playing: {track['name']} by {track['artists'][0]['name']}")

    except Exception as e:
        logger.error(f"Track playback error: {e}")
        await ctx.send(f"Error playing track: {e}")

@bot.command()
async def join(ctx):
    """Join the user's voice channel"""
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return

    voice_channel = ctx.author.voice.channel
    
    if ctx.voice_client is None:
        await voice_channel.connect()
        await ctx.send(f"Joined {voice_channel.name}")
    else:
        await ctx.voice_client.move_to(voice_channel)
        await ctx.send(f"Moved to {voice_channel.name}")

@bot.command()
async def leave(ctx):
    """Leave the current voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")

# Run the bot
def main():
    try:
        bot.run(config.discord_token)
    except Exception as e:
        logger.error(f"Bot runtime error: {e}", exc_info=True)

if __name__ == "__main__":
    main()