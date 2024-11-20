import discord
from discord.ext import commands
from firestore_helper import get_firestore_client
from firebase_admin import firestore
import logging

log = logging.getLogger("GuildEvents")

class GuildEvents(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_firestore_client()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        log.info(f"Joined a new server: {guild.name} (ID: {guild.id})")
        
        # Add the server to the database
        guild_ref = self.db.collection("guilds").document(str(guild.id))
        guild_ref.set({
            "id": guild.id,
            "name": guild.name,
            "invited_on": firestore.SERVER_TIMESTAMP
        })

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        log.info(f"Removed from server: {guild.name} (ID: {guild.id})")
        
        # Remove the server from the database
        guild_ref = self.db.collection("guilds").document(str(guild.id))
        guild_ref.delete()

def setup(bot):
    bot.add_cog(GuildEvents(bot))