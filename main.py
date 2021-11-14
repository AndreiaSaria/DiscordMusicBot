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
# Where did I get this? Here:
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

  @classmethod
  async def from_playlist(cls,url,*,loop=None,stream=False):
    loop = loop or asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
    if 'entries' in data:
      for count, value in enumerate(data):
        data[count] = data['entries'][0]

    return data.get('url')


class GuildData:
  player_url = None
  player_ctx = None
  done = True
  task = None

  def __init__(self, guild):
    self.guild = guild

  async def song_done(self):
    self.done = True
    self.voice_stop()
    print(self.get_voice().voice_members)
    if(len(self.player_url) > 0):
      print(f'Length of queue {len(self.player_url)} on guild {self.guild}')
      await self.play(self.player_ctx[0],self.player_url[0])
      del self.player_url[0]
      del self.player_ctx[0]
    else:
      await self.leave()

  async def leave(self):
    voice = self.get_voice()
    if voice.is_connected:
      await voice.disconnect()

  async def join(self, ctx):
    user = ctx.message.author
    if user.voice is None:
      await ctx.send(user.display_name + " you are not in a voice channel!")
      return False
    vc = user.voice.channel
    voice = self.get_voice()
    if voice == None: 
      await vc.connect()
      await ctx.send(f"Joined **{vc}** voice channel")
  
  async def play(self, ctx, url):
    if self.player_ctx is None:
      self.player_ctx = []
      self.player_url = []

    if(self.done is True):
      if await self.join(ctx) is False:
        return
    
      self.done = False
      async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)

        print(f'Duration {player.duration} in seconds' )
        ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
      self.task = asyncio.create_task(timer(player.duration,self))
      await ctx.send(f'Now playing: {player.title}')
    else:
      self.player_url.append(url)
      self.player_ctx.append(ctx)
      await ctx.send(f"Added '<{url}>' to queue")
      
  async def remove_from_queue(self, ctx, i:int):
    async with ctx.typing():
      if len(self.player_url) < i or i-1 < 0:
        await ctx.send(f"Hey {ctx.message.author.display_name} are you trying to fool me? This is out of the queue's bounds.")
        return
      await ctx.send(f"Removing '<{self.player_url[i-1]}>' from queue")
      del self.player_url[i-1]
      del self.player_ctx[i-1]
      await self.queue(ctx)

  async def queue(self,ctx):
    if len(self.player_url) > 0:
      for count, value in enumerate(self.player_url):
        await ctx.send(f"Number {count + 1} is '<{value}>' sent by {self.player_ctx[count].message.author.display_name}")
    else:
      await ctx.send("I don't have a queue here")

  def get_voice(self):
    return discord.utils.get(bot.voice_clients, guild =self.guild)

  def voice_stop(self):
    voice = self.get_voice()
    voice.stop()

      

global guilds
guilds = []


async def timer(seconds,guildData):
  try:
    await asyncio.sleep(seconds)
  except asyncio.CancelledError:
    print('Timer: cancel sleep')
    raise
  finally:
    print('timer song dome')
    await guildData.song_done()


@bot.command()
async def play(ctx, *, url):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        print(f'Stream on existing guild {value.guild}')
        await guilds[count].play(ctx,url)
        return
    
  guilds.append(GuildData(ctx.guild))
  await guilds[len(guilds)-1].play(ctx,url)

@bot.command()
async def queue(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        await guilds[count].queue(ctx)
        return
  await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def remove_from_queue(ctx, i:int):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        await guilds[count].remove_from_queue(ctx,i)
        return
  await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def skip(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        if value.done is False:
          guilds[count].task.cancel()
          return
        else:
          await ctx.send("I'm not playing a song here")
          return
  await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def stop(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        guilds[count].voice_stop()
        return
      else:
        await ctx.send("I'm not playing a song here")
        return
  await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def leave(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        guilds[count].leave()
        return
  await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def join(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        guilds[count].join(ctx)
        return

  guilds.append(GuildData(ctx.guild))

''''

@bot.command()
async def playlist(ctx,url):
  global guilds
  if len(guilds) > 0:
    for count,value in enumerate(guilds):
      if value.guild is ctx.guild:


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



    @bot.command()
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