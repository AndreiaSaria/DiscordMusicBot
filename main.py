import youtube_dl
import asyncio
import os
from keep_alive import keep_alive
import discord
from discord.ext import commands
from discord.ext.commands import CommandNotFound

#-----AUTENTICATION-----
#Here we do not use the client, we use commands https://discordpy.readthedocs.io/en/stable/ext/commands/commands.html#commands
bot = commands.Bot(command_prefix='--', help_command=None)


#-----BOT MUSIC PLAY (VERY EARLY VER)-----
# Where did I get this? Here:
#https://stackoverflow.com/questions/23727943/how-to-get-information-from-youtube-dl-in-python
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
  async def from_playlist(cls,url):
    ydl = youtube_dl.YoutubeDL({'outtmpl': '%(id)s%(ext)s', 'quiet':True,})
    data = ydl.extract_info(url, download=False)
    video = []

    if 'entries' in data:
      # Can be a playlist or a list of videos
      video = data['entries']

      #loops entries to grab each video_url
      for i, item in enumerate(video):
        video[i] = data['entries'][i]

    return video

  @classmethod
  async def get_title(cls,url):
    ydl = youtube_dl.YoutubeDL({'outtmpl': '%(id)s%(ext)s', 'quiet':True,})
    data = ydl.extract_info(url, download=False)
    if 'entries' in data:
      # Can be a playlist or a list of videos
      return data['entries'][0]['title']

    return data['title']

#Since this bot can run on multiple discord servers (they call them guilds) I made a class to separate each guild's playlist
#This class handles the commands stated down below on --Commands--
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
    if(len(self.player_url) > 0):
      print(f'Length of queue {len(self.player_url)} on guild {self.guild}')
      await self.play(self.player_ctx[0],self.player_url[0])
      del self.player_url[0]
      del self.player_ctx[0]
    #else:
     # await self.leave()

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
      await ctx.send(f"Added '{await YTDLSource.get_title(url)}' to queue")
      
  async def remove_from_queue(self, ctx, i:int):
    if len(self.player_url) < i or i-1 < 0:
      await ctx.send(f"Hey {ctx.message.author.display_name} are you trying to fool me? This is out of the queue's bounds.")
      return
    await ctx.send(f"Removing '{await YTDLSource.get_title(self.player_url[i-1])}' from queue")
    del self.player_url[i-1]
    del self.player_ctx[i-1]
    await self.queue(ctx)

  async def queue(self,ctx):
    
    if len(self.player_url) > 0:
      text = ""
      async with ctx.typing():
        for count, value in enumerate(self.player_url):
          text += (f"\nNumber {count + 1} is '{await YTDLSource.get_title(value)}' sent by {self.player_ctx[count].message.author.display_name}")
        await ctx.send(text)
    else:
      await ctx.send("I don't have a queue here")

  def get_voice(self):
    return discord.utils.get(bot.voice_clients, guild =self.guild)

  def voice_stop(self):
    voice = self.get_voice()
    voice.stop()

  def clear_queue(self,ctx):
    self.player_ctx.clear()
    self.player_url.clear()

      
global guilds
guilds = []

async def timer(seconds,guildData):
  try:
    await asyncio.sleep(seconds)
  except asyncio.CancelledError:
    print('Timer: cancel sleep')
    raise
  finally:
    print('Timer: song dome')
    await guildData.song_done()

def guild_check(ctx):
  global guilds
  if len(guilds) > 0:
    for count, value in enumerate(guilds):
      if value.guild is ctx.guild:
        return True, count
    
  return False, None

#-----COMMANDS-----
@bot.command()
async def play(ctx, *, url):
  exists, count = guild_check(ctx)
  if exists is True:
    print(f'Stream on existing guild {guilds[count].guild}')
    await guilds[count].play(ctx,url)
  else:
    print(f'Adding guild {ctx.guild}')
    guilds.append(GuildData(ctx.guild))
    await guilds[-1].play(ctx,url)

@bot.command()
async def play_playlist(ctx, *, url):
  await ctx.send('I recieved your playlist, calculating links.')
  async with ctx.typing():
    data = await YTDLSource.from_playlist(url)
    await ctx.send(f"Playlist named {data[0]['playlist']}")
  exists, index = guild_check(ctx)
  if exists is False:
    print(f'Adding guild {ctx.guild}')
    guilds.append(GuildData(ctx.guild))
    index = -1
  
  print(f'Stream Playlist on guild {guilds[index].guild}')
  for count, value in enumerate(data):
    await guilds[index].play(ctx,value['webpage_url'])

  print(f'{len(data)} is the length of links')

@bot.command()
async def queue(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    await guilds[count].queue(ctx)
  else:
    await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def remove_from_queue(ctx, i:int):
  exists, count = guild_check(ctx)
  if exists is True:
    await guilds[count].remove_from_queue(ctx,i)
  else:
    await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def skip(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    if guilds[count].done is False:
      guilds[count].task.cancel()
    else:
      await ctx.send("I'm not playing a song here")
  else:
    await ctx.send("Wait a minute, who are you? You are not in my list!")

@bot.command()
async def stop(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    guilds[count].voice_stop()
  else:
    await ctx.send("I'm not playing a song here")


@bot.command()
async def leave(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    await guilds[count].leave()
  else:
    await ctx.send("Wait a minute, who are you?")
  

@bot.command()
async def join(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    await guilds[count].join(ctx)
  else:
    guilds.append(GuildData(ctx.guild))
    await guilds[-1].join(ctx)


@bot.command()
async def clear_queue(ctx):
  exists, count = guild_check(ctx)
  if exists is True:
    guilds[count].clear_queue(ctx)
    await ctx.send('Queue cleared')
  else:
    await ctx.send("Wait a minute, who are you?")

@bot.command()
async def help(ctx):
  await ctx.send("Commands: \n--play 'url' to play a youtube video.\n--play_playlist 'playlist url' plays a youtube playlist by adding all other videos on queue.\n--queue to see the current queue.\n--remove_from_queue 'int: number on queue' to remove a certain video from queue.\n--skip to go to the next song on queue.\n--stop to stop playing audio (it does not clean up the playlist).\n--leave to leave the audio channel.\n--join to manually make the bot join the voice channel.\n--clear_queue to clean the complete queue.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        return
    raise error

#-----STARTING WEB SERVER-----
keep_alive()
#bot.run(os.environ['MYSERVERTOKEN'])
bot.run(os.environ['MUSICBOTTOKEN'])