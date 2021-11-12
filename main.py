import youtube_dl
import asyncio
import os
#from keep_alive import keep_alive
import discord
from discord.ext import commands

#-----AUTENTICATION-----
#Here we do not use the client, we use commands https://discordpy.readthedocs.io/en/stable/ext/commands/commands.html#commands
bot = commands.Bot(command_prefix='--')


#-----BOT MUSIC PLAY (VERY EARLY VER)-----
# Where did I learn how to do this? Here:
#https://stackoverflow.com/questions/64725932/discord-py-send-a-message-if-author-isnt-in-a-voice-channel
#https://stackoverflow.com/questions/61900932/how-can-you-check-voice-channel-id-that-bot-is-connected-to-discord-py
#https://www.youtube.com/watch?v=ml-5tXRmmFk
#https://www.toptal.com/chatbot/how-to-make-a-discord-bot
#https://stackoverflow.com/questions/66610012/discord-py-streaming-youtube-live-into-voice
#https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py

youtube_dl.utils.bug_reports_message = lambda: ''
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
  def __init__(self, source, *, data, volume=0.5):
    super().__init__(source, volume)

    self.data = data

    self.title = data.get('title')
    self.url = data.get('url')
    self.duration = data.get('duration')

  @classmethod
  async def from_url(cls, url, *, loop=None, stream=False):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

    if 'entries' in data:
      # take first item from a playlist
      data = data['entries'][0]

    filename = data['url'] if stream else ytdl.prepare_filename(data)
    return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class PlayerData():

  pass

#guild class with player and task.
player_data = []
queue_ctx = []
queue_url = []
global done
done = True
global task


async def timer(seconds,ctx):
  try:
    await asyncio.sleep(seconds)
  except asyncio.CancelledError:
    print('Timer: cancel sleep')
    raise
  finally:
    print('Timer: after sleep')
    await song_done(ctx)


async def song_done(ctx):
  print('Song done was called')
  global done
  global queue_ctx
  global queue_url

  done = True
  if(len(queue_ctx) > 0):
    print(f'length of queue {len(queue_ctx)}')
    bot.dispatch('stream',queue_ctx[0],queue_url[0])
    del queue_ctx[0]
    del player_data[0]
    del queue_url[0]
  else:
    bot.dispatch('leave',ctx)


@bot.command()
async def join(ctx):
    user = ctx.message.author
    vc = user.voice.channel

    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice == None: # None being the default value if the bot isnt in a channel (which is why the is_connected() is returning errors)
        await vc.connect()
        await ctx.send(f"Joined **{vc}**")
    else:
        print("I'm already connected!")
    
@bot.event
async def on_stream(ctx,url):
  global done
  global task

  if(done is True):
    done = False
    await join(ctx)
    async with ctx.typing():
      player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
      player_data.append(player.data)
      print(f'Duration {player.duration} in seconds' )
      ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
    task = asyncio.create_task(timer(player.duration,ctx))
    await ctx.send(f'Now playing: {player.title}')

@bot.event
async def on_leave(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  if voice.is_connected:
    await voice.disconnect()

@bot.command()
async def stream(ctx, *, url):
  """Streams from a url (same as yt, but doesn't predownload)"""
  global done
  global task #get guild tasks
  global queue_ctx
  global queue_url

  try: 
    task
  except NameError: #or task.done()
  #if(done is True):
    done = False
    await join(ctx)
    async with ctx.typing():
      player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
      player_data.append(player.data)
      print(f'Duration {player.duration} in seconds')
      ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
    task = asyncio.create_task(timer(player.duration,ctx))
    await ctx.send(f'Now playing: {player.title}')
    
  else:
    queue_ctx.append(ctx)
    queue_url.append(url)
    async with ctx.typing():
      player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
      player_data.append(player.data)
    await ctx.send(f'Added to queue: {player.title}')

@bot.command()
async def leave(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  if voice.is_connected:
    await voice.disconnect()

@bot.command()
async def remove_from_queue(ctx, number:int):
  async with ctx.typing():
    await ctx.send(f'Removed {player_data[number].title} from queue')
    del queue_ctx[number]
    del player_data[number]
    del queue_url[number]
    


@bot.command()
async def stop(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  voice.stop()
  '''To cancel a running Task use the cancel() method. Calling it will cause the Task to throw a CancelledError exception into the wrapped coroutine. If a coroutine is awaiting on a Future object during cancellation, the Future object will be cancelled.'''
  #how to cancel asyncio

#Youtube download
@bot.command()
async def yt(ctx, *, url):
  """Plays from a url (almost anything youtube_dl supports)"""

  await join(ctx)
  async with ctx.typing():
    player = await YTDLSource.from_url(url, loop=bot.loop)
    ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)

  await ctx.send(f'Now playing: {player.title}')

@bot.command()
async def play(ctx, *, query):
  """Plays a file from the local filesystem"""

  source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(query))
  ctx.voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)

  await ctx.send(f'Now playing: {query}')



''''    @bot.command()
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @bot.command()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""

        await ctx.voice_client.disconnect()

    @play.before_invoke
    @yt.before_invoke
    @stream.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()
'''

'''@bot.command()
async def play(ctx, url : str):
  song_there = os.path.isfile("song.mp3")
  try:
    if song_there:
      os.remove("song.mp3")
  except PermissionError:
    await ctx.send("Wait for current music to end or use the --stop command")
    return

  voiceChannel = ctx.author.voice
  if voiceChannel:
    voiceChannel = ctx.author.voice.channel
    await voiceChannel.connect()
    voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    ydl_opts = {
      'format': 'bestaudio/best',
      'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
      }],
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
      ydl.download([url])
    for file in os.listdir("./"):
      if file.endswith(".mp3"):
        os.rename(file,"song.mp3")
    voice.play(discord.FFmpegPCMAudio("song.mp3"))
  else:
    print('No voice channel')

@bot.command()
async def leave(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  if voice.is_connected:
    await voice.disconnect()
  else:
    await ctx.send('Bot is not on a voice channel')

@bot.command()
async def pause(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  if voice.is_playing():
    voice.pause()
  else:
    await ctx.send('No audio playing.')

@bot.command()
async def resume(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  if voice.is_paused():
    voice.resume()
  else:
    await ctx.send('The audio is not paused.')

@bot.command()
async def stop(ctx):
  voice = discord.utils.get(bot.voice_clients, guild=ctx.guild)
  voice.stop()'''


#-----STARTING WEB SERVER-----
#keep_alive()
bot.run(os.environ['MYSERVERTOKEN'])
#bot.run(os.environ['NMTOKEN'])