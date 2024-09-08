import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
from notifier import Notifier
import constants

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.message_content = True

GUILD = discord.Object(id=GUILD_ID)

bot = commands.Bot(command_prefix="!", intents=intents)
notifier = Notifier(bot)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")
    await bot.tree.sync(guild=GUILD)
    await notifier.start()


@commands.guild_only()
@bot.tree.command(
    name="set_max_players",
    description="Filter for the maximum number of players in a server. -1 for any.",
)
async def set_max_players(interaction: discord.Interaction, max_players: int):
    notifier.desired_max_players = max_players
    await interaction.response.send_message(
        f"Set max players to {max_players}.", ephemeral=True, delete_after=5
    )


@commands.guild_only()
@bot.tree.command(
    name="set_min_players",
    description="Filter for the minimum number of players in a server. -1 for any.",
)
async def set_min_players(interaction: discord.Interaction, min_players: int):
    notifier.desired_min_players = min_players
    await interaction.response.send_message(
        f"Set min players to {min_players}.", ephemeral=True, delete_after=5
    )


@commands.guild_only()
@bot.tree.command(
    name="set_region", description=f"Set a filter for the region of a server."
)
async def set_region(interaction: discord.Interaction, region: str):
    options = [
        discord.SelectOption(label=region, value=region) for region in constants.regions
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        region = select.values[0]
        notifier.set_region(region)
        await interaction.response.send_message(
            f"Set region to {region}.", ephemeral=True, delete_after=5
        )

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a region:", view=view, ephemeral=True, delete_after=60
    )
    view.stop()


@commands.guild_only()
@bot.tree.command(name="set_map", description=f"Set a filter for the map of a server.")
async def set_map(interaction: discord.Interaction):
    options = [
        discord.SelectOption(label=map, value=map) for map in constants.game_maps
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        map = select.values[0]
        notifier.desired_map = map
        await interaction.response.send_message(
            f"Set map to {map}.", ephemeral=True, delete_after=5
        )

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a map:", view=view, ephemeral=True, delete_after=60
    )
    view.stop()


@commands.guild_only()
@bot.tree.command(
    name="start_notify",
    description=f"Get notified when a server is found with the desired map.",
)
async def start_notify(interaction: discord.Interaction):
    options = [
        discord.SelectOption(label=map, value=map) for map in constants.game_maps
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        map = select.values[0]
        notifier.add_notification(interaction.user, map)
        await interaction.response.send_message(
            f"You will be notified when a server with the map **{map}** is found.",
            ephemeral=True,
            delete_after=5,
        )

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a map:", view=view, ephemeral=True, delete_after=60
    )
    view.stop()


@commands.guild_only()
@bot.tree.command(
    name="stop_notify",
    description=f"Stop getting notified when a server is found with the desired map.",
)
async def stop_notify(interaction: discord.Interaction):
    notified_maps = notifier.get_notified_maps(interaction.user)
    notified_maps.sort()
    options = [discord.SelectOption(label=map, value=map) for map in notified_maps]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        map = select.values[0]
        notifier.remove_notification(interaction.user, map)
        await interaction.response.send_message(
            f"You have been removed from the notification list for the map **{map}**.",
            ephemeral=True,
            delete_after=5,
        )

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a map to stop notifications for:",
        view=view,
        ephemeral=True,
        delete_after=60,
    )
    view.stop()


@commands.guild_only()
@bot.tree.command(
    name="set_channel", description=f"Set the channel to send updates to."
)
async def set_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    purge_channel: bool = False,
):
    await notifier.set_channel(channel, purge_channel)
    await interaction.response.send_message(
        f"Set channel to {channel.mention}.", ephemeral=True, delete_after=5
    )


bot.run(token, log_level=logging.DEBUG)
