import os
import discord
import json
import requests
import random
import asyncio
import dateparser
import re
import time
import aiohttp
import sqlite3
import sys
import subprocess
from datetime import datetime, timedelta
from langdetect import detect, LangDetectException
from discord.ext import commands, tasks
from discord import app_commands
from openai import OpenAI


"""                 Copyright (C) 2024 Kayden Cormier

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>."""


# =======================================================================================================================================
# ==========================================================={BOT STARTS HERE}===========================================================
# =======================================================================================================================================

# --------------------------------------------------INITIALIZATION------------------------------------------------------

# Retrieve your OpenAI API key from an environment variable
openai_api_key = os.getenv('OPENAI_API_KEY')

# Check if the API key is set
if not openai_api_key:
    raise ValueError("The OpenAI API key is not set in the environment variables.")

# Initialize the OpenAI client with the API key
client = OpenAI(api_key=openai_api_key)

# Define intents
intents = discord.Intents.default()
intents.messages = True  # If you need access to messages
intents.message_content = True  
bot = commands.Bot(command_prefix='!', intents=intents)

# Global dictionary to store welcome channel configurations
welcome_channels = {}

# Global dictionary to store temporary configuration data
temp_config = {}

# Event listener for when the bot is ready
@bot.event
async def on_ready():
    # Sync the command tree globally
    await bot.tree.sync()
    global welcome_channels
    welcome_channels = await load_welcome_channels()
    check_birthdays.start()
    print('Kaydonbot  Copyright (C) 2024  Kayden Cormier -- K-GamesMedia')
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    change_status.start()
    print('------')
    
# Status'
@tasks.loop(hours=1)  # Change status every hour
async def change_status():
    await bot.wait_until_ready()
    # Get the number of servers the bot is in
    num_servers = len(bot.guilds)
    # Define the statuses
    statuses = [
        discord.Activity(type=discord.ActivityType.watching, name="/commands"),
        discord.Game(f"in {num_servers} servers"),
        discord.Activity(type=discord.ActivityType.watching, name="twitch.tv/kaydonbob03")
    ]
    # Choose a random status and set it
    current_status = random.choice(statuses) 
    await bot.change_presence(activity=current_status)


@bot.event
async def on_guild_join(guild):
    # Create an embed message
    embed = discord.Embed(
        title="Hello! I'm Kaydonbot",
        description="Thanks for inviting me to your server!",
        color=discord.Color.gold()
    )
    embed.add_field(name="Prefix", value="! for non-slash commands", inline=False)
    embed.add_field(name="Commands", value="Use `/commands` to see all my commands", inline=False)
    embed.set_footer(text="Kaydonbot - Copyright (c) Kayden Cormier -- K-GamesMedia")

       # List of preferred channel names
    preferred_channels = ["welcome", "general", "mod-chat", "mods-only"]

    # Try to find a preferred channel
    for channel_name in preferred_channels:
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if channel and channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)
            return

    # If no preferred channel is found, send in any channel where the bot has permission
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=embed)
            break


@bot.event
async def on_member_join(member):
    # Auto-ban logic
    data = read_hardban()
    guild_id = str(member.guild.id)
    user_id = member.id

    if guild_id in data and user_id in data[guild_id]:
        try:
            await member.ban(reason="User is on the hardban list")
            print(f"Banned user {user_id} from guild {guild_id} (on hardban list)")
            return  # Stop further execution if the member is banned
        except discord.Forbidden:
            print(f"Failed to ban user {user_id} from guild {guild_id} (lack permissions)")
        except Exception as e:
            print(f"Error banning user {user_id} from guild {guild_id}: {e}")

    # Welcome message logic
    if guild_id in welcome_channels and welcome_channels[guild_id].get("enabled", False):
        channel_id = welcome_channels[guild_id].get("channel_id")
        custom_message = welcome_channels[guild_id].get("message", f"Welcome to the server, {member.mention}!")
        channel = member.guild.get_channel(channel_id) if channel_id else None

        if channel:
            await channel.send(custom_message.format(member=member.mention))
    else:
        # Fallback to default message if no custom configuration is found or welcome messages are disabled
        channel = discord.utils.get(member.guild.text_channels, name='welcome')
        if channel:
            await channel.send(f"Welcome to the server, {member.mention}!")

@tasks.loop(hours=6)
async def check_birthdays():
    try:
        today = datetime.datetime.now().strftime('%m-%d')

        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute("SELECT user_id, server_id, birthday FROM birthdays")
        birthdays = c.fetchall()
        conn.close()

        for user_id, server_id, birthday in birthdays:
            # Ignore the year when comparing dates
            if datetime.datetime.strptime(birthday, '%Y-%m-%d').strftime('%m-%d') == today:
                guild = bot.get_guild(int(server_id))
                if guild:
                    user = guild.get_member(int(user_id))
                    if user:
                        # Try to get the #birthdays channel, if not available then #announcements, and finally #general
                        channel = discord.utils.get(guild.text_channels, name='birthdays') or discord.utils.get(guild.text_channels, name='announcements') or discord.utils.get(guild.text_channels, name='general')
                        # If none of the above channels are found, send the message to the first available text channel
                        if not channel and guild.text_channels:
                            channel = guild.text_channels[0]
                        if channel:
                            await channel.send(f"@here please wish a very happy birthday to {user.mention}. Happy Birthday !!!")
    except Exception as e:
        print(f"An error occurred while checking birthdays: {e}")

log_file = "command_log.log"
log_time_limit = timedelta(hours=6)

@bot.event
async def on_command(ctx):
    now = datetime.now()

    # Open the log file in append mode
    with open(log_file, "a") as file:
        # Write the server name, user name and command to the log file
        file.write(f"{now}: Server: {ctx.guild.name}, User: {ctx.author.name}, Command: {ctx.command}\n")

    # Open the log file in read mode
    with open(log_file, "r") as file:
        lines = file.readlines()

    # Filter out lines that are older than the time limit
    lines = [line for line in lines if now - datetime.strptime(line.split(":")[0], "%Y-%m-%d %H:%M:%S.%f") < log_time_limit]

    # Open the log file in write mode and overwrite it with the filtered lines
    with open(log_file, "w") as file:
        file.writelines(lines)


# -------------------------------------------------INITIALIZATION ENDS--------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------COMMANDS LIST-------------------------------------------------------


# Define a slash command for 'commands'
@bot.tree.command(name="commands", description="Get a list off all commands")
async def commands(interaction: discord.Interaction):
    await interaction.response.defer()
    message = await interaction.followup.send(embed=get_general_commands_embed())

    # Add reactions for navigation
    await message.add_reaction("⏪")  # Fast rewind to first page
    await message.add_reaction("⬅️")  # Previous page
    await message.add_reaction("➡️")  # Next page
    await message.add_reaction("⏩")  # Fast forward to last page

def get_general_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot General Commands",
        description="Commands available for all users. Default prefix is ';'",
        color=discord.Color.gold()
    )
    embed.add_field(name="/commands", value="Displays list of all commands", inline=False)
    embed.add_field(name="/hello", value="Bot will say hello", inline=False)
    embed.add_field(name="/chat [prompt]", value="Sends a prompt to the GPT API and returns a response", inline=False)
    embed.add_field(name="/image [prompt]", value="Uses DALL-E 3 to generate an image based on your prompt", inline=False)
    embed.add_field(name="/quote", value="Get an inspirational quote", inline=False)
    embed.add_field(name="/joke", value="Tell a random joke", inline=False)
    embed.add_field(name="/weather [location]", value="Get the current weather for a location", inline=False)
    embed.add_field(name="/reminder [time] [reminder]", value="Set a reminder", inline=False)
    embed.add_field(name="/poll [question] [options]", value="Create a poll", inline=False)
    embed.add_field(name="/random [choices]", value="Make a random choice", inline=False)
    embed.add_field(name="/scream", value="Bot will scream randomly from a list screams", inline=False)
    embed.add_field(name="/screamedit [scream]", value="adds a scream to the list if its not already there", inline=False)
    embed.add_field(name="/userinfo [user]", value="Get information about a user", inline=False)
    embed.add_field(name="/serverinfo", value="Get information about the server", inline=False)
    embed.add_field(name="/birthday [date]", value="Set your birthday", inline=False)
    embed.add_field(name="/upcomingbirthdays", value="Get list of upcoming birthdays within 180 days", inline=False)
    embed.add_field(name="/deletebirthday", value="Delete your birthday", inline=False)
    embed.add_field(name="/birthdaylist", value="Get list of all birthdays", inline=False)
    embed.set_footer(text="Page 1/6")
    return embed

def get_mod_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot Moderator Commands",
        description="Commands available for moderators and administrators.",
        color=discord.Color.green()
    )
    # Add fields for each moderator command
    embed.add_field(name="/welcomeconfig", value="Configuration for user welcome message", inline=False)
    embed.add_field(name="/msgclear [channel] [number]", value="Clear a specified number of messages in a channel", inline=False)
    embed.add_field(name="/mute [member] [duration] [reason]", value="Mute a member", inline=False)
    embed.add_field(name="/unmute [member]", value="Unmute a member", inline=False)
    embed.add_field(name="/lock [channel]", value="Lock a channel", inline=False)
    embed.add_field(name="/unlock [channel]", value="Unlock a channel", inline=False)
    embed.add_field(name="/slowmode [channel] [seconds]", value="Set slowmode in a channel", inline=False)
    embed.add_field(name="/purgeuser [channel] [member] [number]", value="Clear messages by a specific user", inline=False)
    embed.add_field(name="/announce [channel] [message]", value="Send an announcement", inline=False)
    embed.add_field(name="/addrole [member] [role]", value="Add a role to a member", inline=False)
    embed.add_field(name="/removerole [member] [role]", value="Remove a role from a member", inline=False)
    embed.add_field(name="/hardban", value="initiates a setup to add a userid to autoban a user on join to the server", inline=False)
    embed.set_footer(text="Page 3/6")
    return embed

def get_bot_games_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot Bot Games Commands",
        description="Fun games you can play with the bot.",
        color=discord.Color.blue()
    )
    embed.add_field(name="/battle", value="Start a battle game", inline=False)
    embed.add_field(name="/blackjack", value="Play a game of blackjack", inline=False)
    embed.add_field(name="/wouldyourather", value="Play a round of Would You Rather", inline=False)
    embed.add_field(name="/truthordare", value="Play a fun little Truth or Dare game", inline=False)
    # Add more bot game commands here
    embed.set_footer(text="Page 2/6")
    return embed

def get_suggestions_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot Suggestions Commands",
        description="Commands to suggest new features or content for the bot.",
        color=discord.Color.purple()
    )
    embed.add_field(name="/cmdsuggestion [Suggestion]", value="Suggest a new command.", inline=False)
    embed.add_field(name="/tdsuggestion [option] {truth/dare} [suggestion]", value="Suggest a SFW Truth or Dare.", inline=False)
    embed.add_field(name="/wyrsuggestion [suggestion]", value="Suggest a 'Would You Rather' question.", inline=False)
    embed.set_footer(text="Page 6/6")
    return embed

def get_dev_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot Dev Tools Commands",
        description="Commands for use by developers",
        color=discord.Color.blue()
    )
    embed.add_field(name="/sourcecode", value="returns the github repository", inline=False)
    embed.add_field(name="/invite", value="returns the invite link", inline=False)
    embed.add_field(name="/ping", value="gets the bots current ping", inline=False)
    embed.add_field(name="/uptime", value="gets the bots current uptime", inline=False)
    embed.add_field(name="/leaveguild", value="Leaves the current server -authorized users only", inline=False)
    embed.add_field(name="/restart", value="Restarts the bot - authorized users only", inline=False)
    embed.add_field(name="/shutdown", value="Shuts down the bot - authorized users only", inline=False)
    embed.add_field(name="/update", value="Updates the bot - authorized users only", inline=False)
    embed.set_footer(text="Page 5/6")
    return embed

def get_fn_commands_embed():
    embed = discord.Embed(
        title="Kaydonbot Fortnite Commands",
        description="Commands for Fortnite related content",
        color=discord.Color.gold()
    )
    embed.add_field(name="/fnshopcurrent", value="Returns the current item shop", inline=False)
    embed.add_field(name="/fnshopseen [itemname]", value="Retutns information on the item, specifically its last seen info", inline=False)
    embed.add_field(name="/fnshopupcoming", value="Retuns the upcoming item shop", inline=False)
    embed.set_footer(text="Page 4/6")
    return embed

@bot.event
async def on_reaction_add(reaction, user):
    if user != bot.user and reaction.message.author == bot.user:
        embeds = [
            get_general_commands_embed(), 
            get_bot_games_commands_embed(), 
            get_mod_commands_embed(),
            get_fn_commands_embed(),
            get_dev_commands_embed(),
            get_suggestions_commands_embed()
        ]
        current_page = int(reaction.message.embeds[0].footer.text.split('/')[0][-1]) - 1

        if reaction.emoji == "➡️":
            next_page = (current_page + 1) % len(embeds)
            await reaction.message.edit(embed=embeds[next_page])
        elif reaction.emoji == "⬅️":
            next_page = (current_page - 1) % len(embeds)
            await reaction.message.edit(embed=embeds[next_page])
        elif reaction.emoji == "⏩":
            await reaction.message.edit(embed=embeds[-1])  # Go to last page
        elif reaction.emoji == "⏪":
            await reaction.message.edit(embed=embeds[0])  # Go to first page

        await reaction.remove(user)

# --------------------------------------------------COMMANDS LIST ENDS-------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------SUGGESTIONS CMDS--------------------------------------------------------

# Ensure the suggestions directory exists
os.makedirs("suggestions", exist_ok=True)

@bot.tree.command(name="cmdsuggestion", description="Suggest a new command")
async def cmdsuggestion(interaction: discord.Interaction, suggestion: str):
    with open("~/hosting/suggestions/cmd_suggestions.txt", "a") as file:
        file.write(f"{suggestion}\n")
    await interaction.response.send_message("Your command suggestion has been recorded. Thank you!", ephemeral=True)

@bot.tree.command(name="tdsuggestion", description="Suggest a SFW Truth or Dare")
async def tdsuggestion(interaction: discord.Interaction, option: str, suggestion: str):
    filename = "truth_suggestions.txt" if option.lower() == "truth" else "dare_suggestions.txt"
    with open(f"~/hosting/suggestions/{filename}", "a") as file:
        file.write(f"{suggestion}\n")
    await interaction.response.send_message("Your Truth or Dare suggestion has been recorded. Thank you!", ephemeral=True)

@bot.tree.command(name="wyrsuggestion", description="Suggest a 'Would You Rather' question")
async def wyrsuggestion(interaction: discord.Interaction, suggestion: str):
    with open("~/hosting/suggestions/wyr_suggestions.txt", "a") as file:
        file.write(f"{suggestion}\n")
    await interaction.response.send_message("Your 'Would You Rather' suggestion has been recorded. Thank you!", ephemeral=True)




# ----------------------------------------------------SUGGESTIONS ENDS-------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------MOD-ONLY COMMANDS-------------------------------------------------------

# Check if user is admin/mod
def is_admin_or_mod():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator or \
               any(role.name.lower() in ['admin', 'moderator'] for role in interaction.user.roles)
    return app_commands.check(predicate)

#******************************WELCOME MESSAGE******************************

def save_welcome_channels():
    try:
        with open('welcome_channels.json', 'w') as file:
            json.dump(welcome_channels, file, indent=4)
    except Exception as e:
        print(f"Error saving welcome channels: {e}")
        # Consider logging this error or handling it appropriately

async def load_welcome_channels():
    global welcome_channels
    try:
        with open('welcome_channels.json', 'r') as file:
            welcome_channels = json.load(file)
    except FileNotFoundError:
        welcome_channels = {}
        # Consider logging this error or handling it appropriately

@bot.tree.command(name="welcomeconfig", description="Configure the welcome channel")
@is_admin_or_mod()
async def welcomeconfig(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        # Initiate the configuration process
        temp_config[interaction.guild_id] = {"stage": 1}  # Stage 1: Ask to enable/disable

        embed = discord.Embed(
            title="Welcome Configuration",
            description="Welcome to the welcome config settings.\n\n"
                        "1. Please type 'enable' to enable welcome messages or 'disable' to disable them.\n"
                        "2. If enabled, you will be prompted to specify a channel and set a custom welcome message.",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Failed to initiate welcome configuration: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    if guild_id in temp_config:
        if temp_config[guild_id]["stage"] == 1:
            # Handle enabling/disabling welcome messages
            content_lower = message.content.strip().lower()
            if content_lower == 'enable':
                temp_config[guild_id] = {"stage": 2, "enabled": True}  # Move to stage 2
                await message.channel.send("Welcome messages enabled. Please mention the channel for welcome messages.")
            elif content_lower == 'disable':
                welcome_channels[guild_id] = {"enabled": False}
                save_welcome_channels()
                await message.channel.send("Welcome messages will be disabled. They can always be enabled later.")
                del temp_config[guild_id]
            else:
                await message.channel.send("Please type 'enable' or 'disable'.")

        elif temp_config[guild_id]["stage"] == 2:
            # Handle channel selection
            if message.channel_mentions:
                selected_channel = message.channel_mentions[0]
                temp_config[guild_id] = {"stage": 3, "channel_id": selected_channel.id, "enabled": True}  # Move to stage 3
                embed = discord.Embed(
                    title="Welcome Configuration",
                    description="Channel set successfully. Please specify the custom welcome message.",
                    color=discord.Color.green()
                )
                await message.channel.send(embed=embed) 
            else:
                await message.channel.send("Please mention a valid channel.")

        elif temp_config[guild_id]["stage"] == 3:
            # Handle custom welcome message
            custom_message = message.content
            channel_id = temp_config[guild_id]["channel_id"]
            welcome_channels[guild_id] = {"channel_id": channel_id, "message": custom_message, "enabled": True}
            save_welcome_channels()  # Save the configuration

            embed = discord.Embed(
                title="Welcome Configuration",
                description="Custom welcome message set successfully.",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)

            # Clear temporary configuration data
            del temp_config[guild_id]
            


#****************************WELCOME MESSAGE ENDS****************************

# Define a slash command for 'msgclear'
@bot.tree.command(name="msgclear", description="Clear a specified number of messages in a channel")
@is_admin_or_mod()
async def msgclear(interaction: discord.Interaction, channel: discord.TextChannel, number: int):
    try:
        await interaction.response.defer()

        if number < 1 or number > 100:
            await interaction.followup.send("Please specify a number between 1 and 100.")
            return

        messages = [message async for message in channel.history(limit=number)]
        if not messages:
            await interaction.followup.send("No messages to delete.")
            return

        deleted_count = 0
        for message in messages:
            if (discord.utils.utcnow() - message.created_at).days < 14:
                await message.delete()
                deleted_count += 1

        confirmation_message = await interaction.followup.send(f"Cleared {deleted_count} messages in {channel.mention}.")
        await asyncio.sleep(5)  # Wait for 5 seconds
        await confirmation_message.delete()
    except Exception as e:
        await interaction.followup.send(f"Failed to clear messages: {e}")


@bot.tree.command(name="warn", description="Warn a member")
@is_admin_or_mod()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await interaction.response.defer()
        # Send a DM to the member with the warning
        await member.send(f"You have been warned for: {reason}")
        await interaction.followup.send(f"{member.mention} has been warned for: {reason}")
    except Exception as e:
        await interaction.followup.send(f"Failed to warn member: {e}")

@bot.tree.command(name="kick", description="Kick a member from the server")
@is_admin_or_mod()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await interaction.response.defer()
        await member.kick(reason=reason)
        await interaction.followup.send(f"{member.mention} has been kicked for: {reason}")
    except Exception as e:
        await interaction.followup.send(f"Failed to kick member: {e}")

@bot.tree.command(name="ban", description="Ban a member from the server")
@is_admin_or_mod()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await interaction.response.defer()
        await member.ban(reason=reason)
        await interaction.followup.send(f"{member.mention} has been banned for: {reason}")
    except Exception as e:
        await interaction.followup.send(f"Failed to ban member: {e}")

import asyncio

@bot.tree.command(name="mute", description="Mute a member")
@is_admin_or_mod()
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str = "No reason provided"):
    try:
        await interaction.response.defer()
        muted_role = discord.utils.get(member.guild.roles, name="Muted")
        if not muted_role:
            await interaction.followup.send("Muted role not found.")
            return

        await member.add_roles(muted_role, reason=reason)
        await interaction.followup.send(f"{member.mention} has been muted for {duration} minutes. Reason: {reason}")

        await asyncio.sleep(duration * 60)  # Convert minutes to seconds
        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="Mute duration expired")
            await interaction.followup.send(f"{member.mention} has been unmuted.")
    except Exception as e:
        await interaction.followup.send(f"Failed to mute member: {e}")

@bot.tree.command(name="unmute", description="Unmute a member")
@is_admin_or_mod()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    try:
        await interaction.response.defer()
        muted_role = discord.utils.get(member.guild.roles, name="Muted")
        if not muted_role:
            await interaction.followup.send("Muted role not found.")
            return

        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="Manually unmuted")
            await interaction.followup.send(f"{member.mention} has been unmuted.")
        else:
            await interaction.followup.send(f"{member.mention} is not muted.")
    except Exception as e:
        await interaction.followup.send(f"Failed to unmute member: {e}")


@bot.tree.command(name="lock", description="Lock a channel")
@is_admin_or_mod()
async def lock(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        await interaction.response.defer()
        await channel.set_permissions(channel.guild.default_role, send_messages=False)
        await interaction.followup.send(f"{channel.mention} has been locked.")
    except Exception as e:
        await interaction.followup.send(f"Failed to lock the channel: {e}")

@bot.tree.command(name="unlock", description="Unlock a channel")
@is_admin_or_mod()
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        await interaction.response.defer()
        await channel.set_permissions(channel.guild.default_role, send_messages=True)
        await interaction.followup.send(f"{channel.mention} has been unlocked.")
    except Exception as e:
        await interaction.followup.send(f"Failed to unlock the channel: {e}")


@bot.tree.command(name="slowmode", description="Set slowmode in a channel")
@is_admin_or_mod()
async def slowmode(interaction: discord.Interaction, channel: discord.TextChannel, seconds: int):
    try:
        await interaction.response.defer()
        await channel.edit(slowmode_delay=seconds)
        await interaction.followup.send(f"Slowmode set to {seconds} seconds in {channel.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Failed to set slowmode: {e}")


@bot.tree.command(name="purgeuser", description="Clear messages by a specific user")
@is_admin_or_mod()
async def purgeuser(interaction: discord.Interaction, channel: discord.TextChannel, member: discord.Member, number: int):
    try:
        await interaction.response.defer()
        deleted_count = 0
        async for message in channel.history(limit=200):
            if message.author == member and deleted_count < number:
                await message.delete()
                deleted_count += 1
            if deleted_count >= number:
                break
        await interaction.followup.send(f"Cleared {deleted_count} messages from {member.mention} in {channel.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Failed to clear messages: {e}")


@bot.tree.command(name="announce", description="Send an announcement")
@is_admin_or_mod()
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    try:
        await interaction.response.defer(ephemeral=True)
        await channel.send(message)
        # Send a confirmation message that only the command user can see
        await interaction.followup.send(f"Announcement sent in {channel.mention}.", ephemeral=True)
    except Exception as e:
        # If there's an error, send an ephemeral message with the error details
        await interaction.followup.send(f"Failed to send announcement: {e}", ephemeral=True)



@bot.tree.command(name="addrole", description="Add a role to a member")
@is_admin_or_mod()
async def addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await interaction.response.defer()
        if role in member.roles:
            await interaction.followup.send(f"{member.mention} already has the {role.name} role.")
            return

        await member.add_roles(role)
        await interaction.followup.send(f"Added {role.name} role to {member.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Failed to add role: {e}")


@bot.tree.command(name="removerole", description="Remove a role from a member")
@is_admin_or_mod()
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    try:
        await interaction.response.defer()
        if role not in member.roles:
            await interaction.followup.send(f"{member.mention} does not have the {role.name} role.")
            return

        await member.remove_roles(role)
        await interaction.followup.send(f"Removed {role.name} role from {member.mention}.")
    except Exception as e:
        await interaction.followup.send(f"Failed to remove role: {e}")


# Path to the JSON file
hardban_json = 'hardban_list.json'

# Function to read data from the JSON file
def read_hardban():
    if not os.path.exists('hardban_list.json'):
        return {}
    with open('hardban_list.json', 'r') as file:
        return json.load(file)

# Function to write data to the JSON file
def write_json(data):
    with open('hardban_list.json', 'w') as file:
        json.dump(data, file, indent=4)

@bot.tree.command(name="hardban", description="Set up automatic ban for specified users when they join the server")
@is_admin_or_mod()
async def hardban(interaction: discord.Interaction):
    # Sending an initial response
    embed = discord.Embed(title="HardBan Setup",
                          description="Please reply to this message with the user ID or @mention the user to have them automatically banned when they join this server.",
                          color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

    def check(message):
        # Check that the reply is in the same channel and by the user who invoked the command
        return message.channel.id == interaction.channel.id and \
               message.author.id == interaction.user.id

    try:
        reply = await bot.wait_for('message', check=check, timeout=60.0)
        
        # Use regex to find all numbers in the message content, which should correspond to user IDs
        potential_ids = re.findall(r'\d+', reply.content)
        
        # Filter out any numbers that are not 17 to 19 digits long, as Discord IDs are within this range
        valid_user_ids = [uid for uid in potential_ids if 17 <= len(uid) <= 19]

        if not valid_user_ids:
            await interaction.followup.send("No valid user ID found. Please make sure you provide a numeric user ID.", ephemeral=True)
            return
        
        # For this example, we'll just use the first valid ID found
        user_id = int(valid_user_ids[0])
        
        # Read the current data, update it, and write back to the file
        data = read_hardban()
        guild_id = str(interaction.guild_id)
        
        # Add user ID to the list for the guild if not already present
        if guild_id not in data:
            data[guild_id] = []
        if user_id not in data[guild_id]:
            data[guild_id].append(user_id)
            write_json(data)
            await interaction.followup.send(f"User with ID {user_id} has been set for automatic ban on joining.")
        else:
            await interaction.followup.send(f"User with ID {user_id} is already on the hardban list.", ephemeral=True)
        
    except asyncio.TimeoutError:
        await interaction.followup.send("You didn't reply in time!", ephemeral=True)
    except ValueError:
        await interaction.followup.send("An unexpected error occurred while processing the user ID.", ephemeral=True)
    except Exception as e:
        print(f"An error occurred: {e}")  # Debug print
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)





# -------------------------------------------------MOD-ONLY COMMANDS ENDS----------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------OPENAI COMMANDS---------------------------------------------------------

@bot.tree.command(name="chat", description="Get a response from GPT")
async def chat(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()

    async def fetch_response(model):
        try:
            start_time = time.time()
            messages = [{"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}]
            response = await client.chat.completions.create(model=model, messages=messages)
            end_time = time.time()
            print(f"Response from {model} received in {end_time - start_time} seconds")
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error with model {model}: {e}")
            return None

    models = ["gpt-4-1106-preview", "gpt-4", "gpt-3.5-turbo"]
    for model in models:
        response_task = asyncio.create_task(fetch_response(model))
        response = await response_task
        if response:
            await interaction.followup.send(response)
            return

    await interaction.followup.send("Sorry, I'm unable to get a response at the moment.")

async def generate_dalle_image(prompt: str):
    try:
        response = await client.images.generate(model="dall-e-3", prompt=prompt, n=1, size="1024x1024")
        if response.data and len(response.data) > 0:
            image_url = response.data[0].url
            return image_url
        else:
            print("No image data found in the response.")
            return None
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

@bot.tree.command(name="image", description="Generate an image using DALL-E 3")
async def image(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()

    image_url = await generate_dalle_image(prompt)
    if image_url:
        await interaction.followup.send(image_url)
    else:
        await interaction.followup.send("Sorry, I couldn't generate an image.")

# ------------------------------------------------OPENAI COMMANDS ENDS-----------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------GENERAL COMMANDS--------------------------------------------------------

# Define a slash command for 'hello'
@bot.tree.command(name="hello", description="This is just a simple hello command.")  
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello! How are you today?")

@bot.tree.command(name="userinfo", description="Get information about a user")
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    try:
        await interaction.response.defer()
        embed = discord.Embed(title=f"User Info for {member}", color=discord.Color.blue())
        embed.add_field(name="Username", value=str(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Joined at", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Roles", value=" ".join([role.mention for role in member.roles[1:]]), inline=False)
        embed.add_field(name="Status", value=str(member.status).title(), inline=True)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Failed to retrieve user info: {e}")

    
@bot.tree.command(name="serverinfo", description="Get information about the server")
async def serverinfo(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
        guild = interaction.guild
        embed = discord.Embed(title=f"Server Info for {guild.name}", color=discord.Color.green())
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created at", value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        embed.add_field(name="Roles", value=", ".join([role.name for role in guild.roles[1:]]), inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Failed to retrieve server info: {e}")

    
@bot.tree.command(name="poll", description="Create a poll")
async def poll(interaction: discord.Interaction, question: str, options_str: str):
    try:
        await interaction.response.defer()
        options = options_str.split(",")  # Split the options string by commas
        if len(options) < 2:
            await interaction.followup.send("Please provide at least two options for the poll, separated by commas.")
            return

        embed = discord.Embed(title="Poll", description=question, color=discord.Color.blue())
        reactions = ['🔵', '🔴', '🟢', '🟡', '🟣', '🟠', '⚫', '⚪']  # Add more if needed

        poll_options = {reactions[i]: option.strip() for i, option in enumerate(options) if i < len(reactions)}
        for emoji, option in poll_options.items():
            embed.add_field(name=emoji, value=option, inline=False)

        poll_message = await interaction.followup.send(embed=embed)
        for emoji in poll_options.keys():
            await poll_message.add_reaction(emoji)
    except Exception as e:
        await interaction.followup.send(f"Failed to create poll: {e}")


@bot.tree.command(name="random", description="Make a random choice")
async def random_choice(interaction: discord.Interaction, choices_str: str):
    try:
        await interaction.response.defer()
        choices = choices_str.split(",")  # Split the choices string by commas
        if len(choices) < 2:
            await interaction.followup.send("Please provide at least two choices, separated by commas.")
            return

        selected_choice = random.choice(choices).strip()  
        await interaction.followup.send(f"Randomly selected: {selected_choice}")
    except Exception as e:
        await interaction.followup.send(f"Failed to make a random choice: {e}")


@bot.tree.command(name="weather", description="Get the current weather for a location")
async def weather(interaction: discord.Interaction, location: str):
    try:
        await interaction.response.defer()
        api_key = os.getenv("OPENWEATHER_API_KEY")  # Fetch the API key from an environment variable
        if not api_key:
            await interaction.followup.send("Weather API key not set.")
            return

        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
        response = requests.get(url).json()

        if response.get("cod") != 200:
            await interaction.followup.send(f"Failed to retrieve weather info for {location}.")
            return

        weather_description = response['weather'][0]['description']
        temperature = response['main']['temp']
        humidity = response['main']['humidity']
        wind_speed = response['wind']['speed']

        weather_info = (f"Weather in {location.title()}: {weather_description}\n"
                        f"Temperature: {temperature}°C\n"
                        f"Humidity: {humidity}%\n"
                        f"Wind Speed: {wind_speed} m/s")

        await interaction.followup.send(weather_info)
    except Exception as e:
        await interaction.followup.send(f"Failed to retrieve weather info: {e}")
    
@bot.tree.command(name="reminder", description="Set a reminder")
async def reminder(interaction: discord.Interaction, time: str, reminder: str):
    try:
        await interaction.response.defer()
        # Parse the time string into a datetime object
        reminder_time = dateparser.parse(time)
        if not reminder_time:
            await interaction.followup.send("Invalid time format.")
            return

        # Calculate the delay in seconds
        delay = (reminder_time - datetime.datetime.now()).total_seconds()
        if delay < 0:
            await interaction.followup.send("Time is in the past.")
            return

        # Wait for the specified time and send the reminder
        await asyncio.sleep(delay)
        await interaction.followup.send(f"Reminder: {reminder}")
    except Exception as e:
        await interaction.followup.send(f"Failed to set reminder: {e}")


@bot.tree.command(name="quote", description="Get an inspirational quote")
async def quote(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
        response = requests.get("https://zenquotes.io/api/random")
        if response.status_code != 200:
            await interaction.followup.send("Failed to retrieve a quote.")
            return

        quote_data = response.json()[0]
        quote_text = f"{quote_data['q']} - {quote_data['a']}"
        await interaction.followup.send(quote_text)
    except Exception as e:
        await interaction.followup.send(f"Failed to retrieve a quote: {e}")
    
@bot.tree.command(name="joke", description="Tell a random joke")
async def joke(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
        headers = {'Accept': 'application/json'}
        response = requests.get("https://icanhazdadjoke.com/", headers=headers)
        if response.status_code != 200:
            await interaction.followup.send("Failed to retrieve a joke.")
            return

        joke_text = response.json()['joke']
        await interaction.followup.send(joke_text)
    except Exception as e:
        await interaction.followup.send(f"Failed to retrieve a joke: {e}")

# Path to the JSON file for screams
scream_json = 'random_scream.json'

# Path to the JSON file for blacklist
wordblacklist_json = 'complete_words_blacklist.json'

# Function to read data from the JSON file
def read_screams():
    with open(scream_json, 'r') as file:
        return json.load(file)['screams']

# Function to read the blacklist from the JSON file
def read_blacklist():
    with open(wordblacklist_json, 'r') as file:
        return json.load(file)['blacklist']

# Function to write data to the JSON file
def write_screams(screams):
    with open(scream_json, 'w') as file:
        json.dump({'screams': screams}, file, indent=4)

@bot.tree.command(name="scream", description="Let out a random scream")
async def scream(interaction: discord.Interaction):
    screams = read_screams()
    random_scream = random.choice(screams)
    await interaction.response.send_message(f"# {random_scream}")

@bot.tree.command(name="screamedit", description="Adds a scream to the list if it's not already there")
async def screamedit(interaction: discord.Interaction, scream: str):
    # Acknowledge the interaction immediately but indicate that you're still working on it
    await interaction.response.defer(ephemeral=True)

    # Regex to block URLs
    if re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', scream):
        await interaction.followup.send("Links are not allowed in screams. Please try again.", ephemeral=True)
        return
    
    # Remove any '#' characters, trim whitespace, and convert to uppercase
    scream_sanitized = re.sub(r'#', '', scream).strip().upper()

    # # Attempt to detect the language of the scream
    # try:
    #     if detect(scream_sanitized) != 'en':
    #         await interaction.followup.send("Only English screams are allowed. Please try again.", ephemeral=True)
    #         return
    # except LangDetectException:
    #     await interaction.followup.send("The language of your scream could not be determined. Please ensure it is English.", ephemeral=True)
    #     return

    # Regular expression pattern for matching variations of the nword with whitespace in between letters
    nword_pattern = re.compile(r'n\s*i\s*g\s*g\s*e\s*r', re.IGNORECASE)

    # Remove all whitespace from the scream for the purpose of blacklist checking
    scream_for_blacklist_check = re.sub(r'\s+', '', scream_sanitized).lower()

    # Regex to remove repeated characters (more than 2 of the same character in a row) for blacklist checking
    scream_for_blacklist_check = re.sub(r'(.)\1{2,}', r'\1', scream_for_blacklist_check)

    # Read the blacklist
    blacklist = read_blacklist()

    # Check if the scream for blacklist check contains any blacklisted substrings or the nword pattern
    if any(blacklisted_word in scream_for_blacklist_check for blacklisted_word in blacklist) or nword_pattern.search(scream_for_blacklist_check):
        await interaction.followup.send("Your scream contains inappropriate content. Please try again without using offensive language.", ephemeral=True)
        return

    # Read the current list of screams
    screams = read_screams()

    # Check if the scream is already in the list
    if scream_sanitized in screams: 
        await interaction.followup.send("That scream is already in the list!", ephemeral=True)
        return

    # Add the new scream to the list and write back to the JSON file
    screams.append(scream_sanitized)
    write_screams(screams)

    # Send the final response
    await interaction.followup.send(f"New scream added to the list: {scream_sanitized}", ephemeral=True)



# global dictionary for keeping track of 
to_reply = {}

# Funny secret command
@bot.tree.command(name="omega", description="Secret Command to WHOMEGALUL someone")
async def scream(interaction: discord.Interaction, user: discord.User):
    to_reply[user.id] = True
    await interaction.response.send_message(f"Will reply to {user.mention} next time they send a message.", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.id in to_reply:
        await message.channel.send(f"# WH<:OMEGALUL:1165130819275346012>")
        del to_reply[message.author.id]
    await bot.process_commands(message)

@bot.tree.command(name="urban", description="Search Urban Dictionary")
async def urban(interaction: discord.Interaction, term: str):
    await interaction.response.defer()

    url = f"http://api.urbandictionary.com/v0/define?term={term}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['list']:
                        definition = data['list'][0]['definition']
                        await interaction.followup.send(definition[:2000])  # Trim message to fit Discord limit
                    else:
                        await interaction.followup.send("No definition found for the term.")
                else:
                    await interaction.followup.send("Failed to fetch data from Urban Dictionary.")
        except aiohttp.ClientError as e:
            print(f"Failed to fetch Urban Dictionary data: {e}")
            await interaction.followup.send("Encountered an error while fetching data.")

conn = sqlite3.connect('birthdays.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS birthdays
             (user_id text, server_id text, birthday text, PRIMARY KEY(user_id, server_id))''')
conn.commit()
conn.close()

@bot.tree.command(name="birthday", description="Set your birthday")
async def birthday(interaction: discord.Interaction, date: str):
    try:
        await interaction.response.defer()
        # Parse the date string into a datetime object
        birthday_date = dateparser.parse(date)
        if not birthday_date:
            await interaction.followup.send("Invalid date format.")
            return

        # Save the birthday in the database
        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO birthdays VALUES (?, ?, ?)''',
                  (interaction.user.id, interaction.guild.id, birthday_date.strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"Your birthday is set to: {birthday_date.strftime('%Y-%m-%d')}")
    except Exception as e:
        await interaction.followup.send(f"Failed to set birthday: {e}")


@bot.tree.command(name="upcomingbirthdays", description="Get upcoming birthdays for the next 180 days")
async def upcoming_birthdays(interaction: discord.Interaction):
    try:
        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute("SELECT user_id, birthday FROM birthdays WHERE server_id = ?", (interaction.guild.id,))
        birthdays = c.fetchall()
        conn.close()

        if not birthdays:
            await interaction.response.send_message("No upcoming birthdays found.")
            return

        upcoming_birthdays = []
        for user_id, birthday in birthdays:
            birthday_date = dateparser.parse(birthday)
            if birthday_date:
                # Adjust the year of the birthday to this year for comparison
                birthday_date = birthday_date.replace(year=datetime.now().year)

                # Check if the birthday is within the next 2 months
                if datetime.now() <= birthday_date <= datetime.now() + timedelta(days=180):
                    upcoming_birthdays.append((user_id, birthday_date))

        if not upcoming_birthdays:
            await interaction.response.send_message("No upcoming birthdays found.")
            return

        upcoming_birthdays.sort(key=lambda x: x[1])  # Sort by birthday date
        birthday_info = "\n".join([f"<@{user_id}> - {birthday_date.strftime('%B %d')}" for user_id, birthday_date in upcoming_birthdays])

        embed = discord.Embed(title="Upcoming birthdays", description=birthday_info, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"Failed to retrieve upcoming birthdays: {e}")


@bot.tree.command(name="deletebirthday", description="Delete your birthday")
async def delete_birthday(interaction: discord.Interaction):
    try:
        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute("DELETE FROM birthdays WHERE user_id = ? AND server_id = ?", (interaction.user.id, interaction.guild.id))
        conn.commit()
        conn.close()

        await interaction.response.send_message("Your birthday has been deleted.")
    except Exception as e:
        await interaction.response.send_message(f"Failed to delete birthday: {e}")

@bot.tree.command(name="birthdayinfo", description="Get the birthday of a user")
async def birthday_info(interaction: discord.Interaction, user: discord.User):
    try:
        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute("SELECT birthday FROM birthdays WHERE user_id = ? AND server_id = ?", (user.id, interaction.guild.id))
        birthday = c.fetchone()
        conn.close()

        if not birthday:
            await interaction.response.send_message("No birthday found for the user.")
            return

        birthday_date = dateparser.parse(birthday[0])
        if not birthday_date:
            await interaction.response.send_message("Invalid date format.")
            return

        await interaction.response.send_message(f"{user.mention}'s birthday is: {birthday_date.strftime('%Y-%m-%d')}")
    except Exception as e:
        await interaction.response.send_message(f"Failed to retrieve birthday: {e}")

@bot.tree.command(name="birthdayslist", description="See all birthdays")
async def birthdays_all(interaction: discord.Interaction):
    try:
        conn = sqlite3.connect('birthdays.db')
        c = conn.cursor()
        c.execute("SELECT user_id, birthday FROM birthdays WHERE server_id = ?", (interaction.guild.id,))
        birthdays = c.fetchall()
        conn.close()

        if not birthdays:
            await interaction.response.send_message("No birthdays found.")
            return

        birthday_info = "\n".join([f"<@{user_id}> - {dateparser.parse(birthday).strftime('%Y-%m-%d')}" for user_id, birthday in birthdays])
        embed = discord.Embed(title="Birthdays", description=birthday_info, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"Failed to retrieve birthdays: {e}")

# ------------------------------------------------GENERAL COMMANDS ENDS----------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------DEV COMMANDS---------------------------------------------------------
    
@bot.tree.command(name="sourcecode", description="Get the source code for this bot")
async def sourcecode(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="Source Code", description="Get the source code for this bot", 
                  url="https://github.com/Kaydonbob03/kaydonbotv2", color=0x5CDBF0)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="invite", description="Get the invite link for this bot")
async def sourcecode(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="Invite Bot", description="Invite this bot to your server", 
                  url="https://discord.com/oauth2/authorize?client_id=1181143854959837184&permissions=8&scope=bot+applications.commands", color=discord.Color.gold())
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="restart", description="Restart the bot")
async def restart(interaction: discord.Interaction):
    # Load the authorized user IDs from the JSON file
    with open("authorized_users.json", "r") as file:
        authorized_users = json.load(file)["users"]

    # Check if the user who invoked the command is authorized
    if str(interaction.user.id) in authorized_users:
        await interaction.response.send_message("Restarting...", ephemeral=True)
        subprocess.Popen(["sudo", "/home/kayden/hosting/restart_bot.sh"])
    else:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)

@bot.tree.command(name="botupdate", description="Update and restart the bot")
async def updater(interaction: discord.Interaction):
    # Load the authorized user IDs from the JSON file
    with open("authorized_users.json", "r") as file:
        authorized_users = json.load(file)["users"]

    # Check if the user who invoked the command is authorized
    if str(interaction.user.id) in authorized_users:
        await interaction.response.send_message("Updating and restarting...", ephemeral=True)
        subprocess.Popen(["sudo", "/home/kayden/hosting/update_bot.sh"])
    else:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)

@bot.tree.command(name="ping", description="Get the bot's latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="uptime", description="Get the bot's uptime")
async def uptime(interaction: discord.Interaction):
    uptime = datetime.now() - bot.start_time
    await interaction.response.send_message(f"Uptime: {uptime}")

@bot.tree.command(name="shutdown", description="Shutdown the bot")
async def shutdown(interaction: discord.Interaction):
    # Load the authorized user IDs from the JSON file
    with open("authorized_users.json", "r") as file:
        authorized_users = json.load(file)["users"]

    # Check if the user who invoked the command is authorized
    if str(interaction.user.id) in authorized_users:
        await interaction.response.send_message("Shutting down...", ephemeral=True)
        await bot.close()
    else:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)

@bot.tree.command(name="leaveguild", description="Leave a guild")
async def leave_guild(interaction: discord.Interaction, guild_id: int):
    # Load the authorized user IDs from the JSON file
    with open("authorized_users.json", "r") as file:
        authorized_users = json.load(file)["users"]

    # Check if the user who invoked the command is authorized
    if str(interaction.user.id) in authorized_users:
        guild = bot.get_guild(guild_id)
        if guild:
            await guild.leave()
            await interaction.response.send_message(f"Left guild: {guild_id}", ephemeral=True)
        else:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
    else:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)

@bot.tree.command(name="listguilds", description="List all guilds the bot is in")
async def list_guilds(interaction: discord.Interaction):
    # Load the authorized user IDs from the JSON file
    with open("authorized_users.json", "r") as file:
        authorized_users = json.load(file)["users"]

    # Check if the user who invoked the command is authorized
    if str(interaction.user.id) in authorized_users:
        guilds = [guild.name for guild in bot.guilds]
        await interaction.response.send_message(f"Guilds: {', '.join(guilds)}")
    else:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)



# ---------------------------------------------------DEV COMMANDS ENDS-------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------
# ------------------------------------------------------FNBR COMMANDS--------------------------------------------------------


@bot.tree.command(name="fnshopcurrent", description="Displays the current Fortnite item shop")
async def fnshopcurrent(interaction: discord.Interaction):
    await interaction.response.defer()

    api_url = "https://fnbr.co/api/shop"
    headers = {"x-api-key": os.getenv("FNBR_API_KEY")}

    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as response:
            if response.status == 200:
                shop_data = await response.json()
                date = shop_data['data'].get('date', 'Unknown date')

                # Initialize the first embed
                embed = discord.Embed(title="Fortnite Item Shop", description=f"Shop for {date}", color=discord.Color.blue())
                embeds = [embed]  # List to hold all embeds
                current_embed = embed  # Reference to the current embed being added to

                sections = shop_data['data'].get('sections', [])
                for section in sections:
                    section_name = section.get('displayName', 'Unknown Section')
                    items = section.get('items', [])
                    item_names = []  # Collect item names to display in one field

                    for item_id in items:
                        # Use the item ID to fetch the details from the images endpoint
                        item_url = f"https://fnbr.co/api/images?search={item_id}"
                        async with session.get(item_url, headers=headers) as item_response:
                            if item_response.status == 200:
                                item_data = await item_response.json()
                                item_names.append(item_data['data'][0]['name'])  # Assuming first result is the name
                            else:
                                item_names.append("Details unavailable")

                        # Check if the current embed has reached the field limit
                        if len(current_embed.fields) == 25:
                            # Create a new embed and add it to the list
                            current_embed = discord.Embed(title="Fortnite Item Shop Continued...", color=discord.Color.blue())
                            embeds.append(current_embed)

                    # Add a single field to the current embed with all item names for this section
                    if item_names:  # Only add the field if there are item names
                        current_embed.add_field(name=section_name, value="\n".join(item_names), inline=False)
                    await asyncio.sleep(0.1)  # Sleep to prevent rate limit issues

                # Send all the embeds
                for embed in embeds:
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Failed to fetch the current item shop. Please try again later.")


#---


@bot.tree.command(name="fnshopseen", description="Shows the last time an item was seen in the Fortnite item shop")
async def fnshopseen(interaction: discord.Interaction, itemname: str):
    await interaction.response.defer(ephemeral=False)

    api_url = f"https://fnbr.co/api/images?search={itemname}"
    headers = {"x-api-key": os.getenv("FNBR_API_KEY")}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    await interaction.followup.send("Failed to fetch data from the FNBR API. Please try again later.")
                    return
                
                data = await response.json()
                if data['status'] != 200 or not data['data']:
                    await interaction.followup.send("Item not found. Please check the item name and try again.")
                    return
                
                # Assuming the first result is the most relevant
                item = data['data'][0]
                name = item.get('name', 'Unknown Item')
                description = item.get('description', 'No description available.')
                price = item.get('price', 'Unknown Price')
                last_seen = item.get('seen', 'Unknown')
                rarity = item.get('rarity', 'Unknown Rarity').capitalize()
                icon_url = item.get('images', {}).get('icon', '')
                
                embed = discord.Embed(title=name, description=description, color=discord.Color.blue())
                embed.add_field(name="Rarity", value=rarity, inline=False)
                embed.add_field(name="Price", value=price, inline=False)
                embed.add_field(name="Last Seen", value=last_seen, inline=False)
                
                if icon_url:
                    embed.set_thumbnail(url=icon_url)
                
                await interaction.followup.send(embed=embed)

        except aiohttp.ClientError:
            await interaction.followup.send("Encountered an error while fetching data. Please try again later.")

@bot.tree.command(name="fnshopupcoming", description="Displays upcoming items in the Fortnite item shop")
async def fnshopupcoming(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    api_url = "https://fnbr.co/api/upcoming"
    headers = {"x-api-key": os.getenv("FNBR_API_KEY")}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers) as response:
                if response.status != 200:
                    # Log or print the response status for debugging
                    print(f"Unexpected response {response.status} from FNBR API.")
                    await interaction.followup.send("Failed to fetch data from the FNBR API. Please try again later.")
                    return
                
                data = await response.json()
                # Check for proper status in the JSON data
                if data.get('status') != 200:
                    print(f"FNBR API error response: {data.get('error', 'No error message provided.')}")
                    await interaction.followup.send("There was an error fetching upcoming items. Please try again later.")
                    return

                upcoming_items = data.get('data')
                if not upcoming_items:
                    await interaction.followup.send("There are no upcoming items found. Please check back later.")
                    return

                embed = discord.Embed(title="Upcoming Fortnite Items", description="Here are the items expected to arrive in the Fortnite item shop soon.", color=discord.Color.dark_gold())
                for item in upcoming_items[:10]:  # Limit to first 10 items to avoid embed limits
                    name = item.get('name', 'Unknown Item')
                    rarity = item.get('rarity', 'Unknown Rarity').capitalize()
                    item_type = item.get('type', 'Unknown Type').capitalize()
                    icon_url = item.get('images', {}).get('icon', '')
                    
                    embed_value = f"Rarity: {rarity}\nType: {item_type}"
                    embed.add_field(name=name, value=embed_value, inline=False)
                    if icon_url:
                        embed.set_thumbnail(url=icon_url)  # Consider using set_thumbnail for a single image

                await interaction.followup.send(embed=embed)

        except aiohttp.ClientError as e:
            print(f"AIOHTTP client error: {e}")
            await interaction.followup.send("Encountered an error while trying to communicate with the FNBR API. Please try again later.")
        except Exception as e:
            # Catch-all for any other errors
            print(f"An unexpected error occurred: {e}")
            await interaction.followup.send("An unexpected error occurred. Please try again later.")


# ---------------------------------------------------FNBR COMMANDS ENDS------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------BOT GAMES-----------------------------------------------------------



# _________________________________________________BLACKJACK_____________________________________________

# Define card values
card_values = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11
}

# Function to draw a card
def draw_card():
    card = random.choice(list(card_values.keys()))
    suit = random.choice(['♠', '♦', '♣', '♥'])
    return f"{card}{suit}"

# Function to calculate the score of a hand
def calculate_score(hand):
    score = sum(card_values[card[:-1]] for card in hand)
    # Adjust for Aces
    for card in hand:
        if card[:-1] == 'A' and score > 21:
            score -= 10
    return score

# Function to check for Blackjack
def is_blackjack(hand):
    return calculate_score(hand) == 21 and len(hand) == 2

# Function to update the game message
async def update_game_message(message, player_hand, dealer_hand, game_over=False):
    player_score = calculate_score(player_hand)
    dealer_score = calculate_score(dealer_hand) if game_over else '?'
    dealer_display = " ".join(dealer_hand) if game_over else dealer_hand[0] + " ?"

    embed = discord.Embed(title="Blackjack", color=discord.Color.green())
    embed.add_field(name="Your Hand", value=" ".join(player_hand) + f" (Score: {player_score})", inline=False)
    embed.add_field(name="Dealer's Hand", value=dealer_display + f" (Score: {dealer_score})", inline=False)

    if game_over:
        if player_score > 21:
            embed.set_footer(text="You busted! Dealer wins.")
        elif dealer_score > 21 or player_score > dealer_score:
            embed.set_footer(text="You win!")
        elif player_score == dealer_score:
            embed.set_footer(text="It's a tie!")
        else:
            embed.set_footer(text="Dealer wins.")

    await message.edit(embed=embed)

# Blackjack command
@bot.tree.command(name="blackjack", description="Play a game of blackjack")
async def blackjack(interaction: discord.Interaction):
    player_hand = [draw_card(), draw_card()]
    dealer_hand = [draw_card(), draw_card()]

    # Check for Blackjack on initial deal
    if is_blackjack(player_hand) or is_blackjack(dealer_hand):
        await interaction.response.send_message("Checking for Blackjack...")
        await update_game_message(message, player_hand, dealer_hand, game_over=True)
        return

    message = await interaction.response.send_message("Starting Blackjack game...")
    await update_game_message(message, player_hand, dealer_hand)

    # Add reactions for player actions
    await message.add_reaction('♠')  # Hit
    await message.add_reaction('♦')  # Stand

    def check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in ['♠', '♦'] and reaction.message.id == message.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)

        if str(reaction.emoji) == '♠':  # Hit
            player_hand.append(draw_card())
            if calculate_score(player_hand) > 21:
                await update_game_message(message, player_hand, dealer_hand, game_over=True)
            else:
                await update_game_message(message, player_hand, dealer_hand)
        elif str(reaction.emoji) == '♦':  # Stand
            while calculate_score(dealer_hand) < 17:
                dealer_hand.append(draw_card())
            await update_game_message(message, player_hand, dealer_hand, game_over=True)

    except asyncio.TimeoutError:
        await message.clear_reactions()
        await message.edit(content="Blackjack game timed out.", embed=None)
# _________________________________________________BLACKJACK ENDS_____________________________________________

# _________________________________________________BATTLE GAME________________________________________________

# Global dictionary to store game states
game_states = {}

# Define the battle command
@bot.tree.command(name="battle", description="Start a battle game")
async def battle(interaction: discord.Interaction):
    player_health = 100
    bot_health = 100
    embed = discord.Embed(title="Battle Game", description="Choose your action!", color=discord.Color.red())
    embed.add_field(name="Your Health", value=str(player_health), inline=True)
    embed.add_field(name="Bot's Health", value=str(bot_health), inline=True)
    embed.add_field(name="Actions", value="⚔️ to attack\n🛡️ to defend", inline=False)

    message = await interaction.response.send_message(embed=embed)

    # Add reactions for game actions
    await message.add_reaction('⚔️')  # Attack
    await message.add_reaction('🛡️')  # Defend

    # Store initial game state
    game_states[message.id] = {
        "player_health": player_health,
        "bot_health": bot_health,
        "interaction": interaction
    }

# Handle reactions
@bot.event
async def on_reaction_add_battle(reaction, user):
    if user != bot.user and reaction.message.id in game_states:
        game_state = game_states[reaction.message.id]
        interaction = game_state["interaction"]

        if user.id != interaction.user.id:
            return  # Ignore reactions from other users

        player_action = reaction.emoji
        bot_action = random.choice(['⚔️', '🛡️'])

        # Determine the outcome of the turn
        if player_action == '⚔️' and bot_action == '⚔️':
            game_state["player_health"] -= 10
            game_state["bot_health"] -= 10
        elif player_action == '⚔️' and bot_action == '🛡️':
            game_state["bot_health"] -= 5
        elif player_action == '🛡️' and bot_action == '⚔️':
            game_state["player_health"] -= 5

        # Update the embed with the new health values
        embed = discord.Embed(title="Battle Game", description="Choose your action!", color=discord.Color.red())
        embed.add_field(name="Your Health", value=str(game_state["player_health"]), inline=True)
        embed.add_field(name="Bot's Health", value=str(game_state["bot_health"]), inline=True)
        embed.add_field(name="Bot's Action", value="Bot chose to " + ("attack" if bot_action == '⚔️' else "defend"), inline=False)

        await reaction.message.edit(embed=embed)

        # Check for end of game
        if game_state["player_health"] <= 0 or game_state["bot_health"] <= 0:
            winner = "You win!" if game_state["player_health"] > game_state["bot_health"] else "Bot wins!"
            await reaction.message.edit(content=winner, embed=None)
            del game_states[reaction.message.id]  # Clean up the game state
            return

        # Prepare for the next turn
        await reaction.message.clear_reactions()
        await reaction.message.add_reaction('⚔️')  # Attack
        await reaction.message.add_reaction('🛡️')  # Defend
# _________________________________________________BATTLE GAME ENDS________________________________________________


# _________________________________________________WOULD YOU RATHER________________________________________________


# Load Would You Rather questions from JSON file
def load_wyr_questions():
    with open('wouldyourather.json', 'r') as file:
        return json.load(file)

# Define the Would You Rather command
@bot.tree.command(name="wouldyourather", description="Play 'Would You Rather'")
async def wouldyourather(interaction: discord.Interaction):
    await interaction.response.defer()
    questions = load_wyr_questions()
    question = random.choice(questions)

    embed = discord.Embed(title="Would You Rather", description=question["question"], color=discord.Color.blue())
    embed.add_field(name="Option 1", value=question["option1"], inline=False)
    embed.add_field(name="Option 2", value=question["option2"], inline=False)

    message = await interaction.followup.send(embed=embed)  # Use followup.send

    # Add reactions for options
    await message.add_reaction("1️⃣")  # Option 1
    await message.add_reaction("2️⃣")  # Option 2

    # Wait for a reaction
    def wyr_check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in ["1️⃣", "2️⃣"] and reaction.message.id == message.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=wyr_check)
        choice_key = "option1" if str(reaction.emoji) == "1️⃣" else "option2"
        await interaction.followup.send(f"{user.mention} chose {choice_key.replace('option', 'Option ')}: {question[choice_key]}")
    except asyncio.TimeoutError:
        await message.clear_reactions()
        await message.edit(content="Would You Rather game timed out.", embed=None)

# _________________________________________________WOULD YOU RATHER ENDS____________________________________________

# ______________________________________________________TRUTH OR DARE_______________________________________________

# Load Truth or Dare questions from JSON file
def load_tod_questions():
    with open('truthordare.json', 'r') as file:
        return json.load(file)

# Define the Truth or Dare command
@bot.tree.command(name="truthordare", description="Play 'Truth or Dare'")
async def truth_or_dare(interaction: discord.Interaction):
    await interaction.response.defer()
    questions = load_tod_questions()

    embed = discord.Embed(title="Truth or Dare", description="React with 🤔 for Truth or 😈 for Dare", color=discord.Color.blue())
    message = await interaction.followup.send(embed=embed)

    if message:
        await message.add_reaction("🤔")  # Truth
        await message.add_reaction("😈")  # Dare

    # Wait for a reaction
    def tod_check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in ["🤔", "😈"] and reaction.message.id == message.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=tod_check)
        if str(reaction.emoji) == "🤔":
            selected = random.choice(questions['truths'])
            response_type = "Truth"
        else:
            selected = random.choice(questions['dares'])
            response_type = "Dare"

        response_embed = discord.Embed(
            title=f"{response_type} for {user.display_name}",
            description=selected,
            color=discord.Color.green() if response_type == "Truth" else discord.Color.red()
        )
        await interaction.followup.send(embed=response_embed)
    except asyncio.TimeoutError:
        await message.clear_reactions()
        await message.edit(content="Truth or Dare game timed out.", embed=None)

# ________________________________________________TRUTH OR DARE ENDS________________________________________________
# --------------------------------------------------BOT GAMES END----------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------BOT TOKEN BELOW---------------------------------------------------------



# Run the bot with your token
bot.run(os.getenv('DISCORD_BOT_TOKEN'))

# --------------------------------------------------BOT TOKEN ENDS--------------------------------------------------------

# ========================================================================================================================
