import discord
from discord.ext import commands
from googletrans import Translator as GoogleTranslator

class Translator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.translator = GoogleTranslator()

        # Mapping of emoji flags to language codes
        self.flag_to_language = {
            "🇺🇸": "en",  # English
            "🇫🇷": "fr",  # French
            "🇪🇸": "es",  # Spanish
            "🇩🇪": "de",  # German
            "🇮🇹": "it",  # Italian
            "🇷🇺": "ru",  # Russian
            "🇨🇳": "zh-cn",  # Chinese
            "🇯🇵": "ja",  # Japanese
        }

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        # Ensure it's not a bot and it's reacting to a message
        if user.bot or reaction.message is None:
            return

        emoji = str(reaction.emoji)
        language_code = self.flag_to_language.get(emoji)

        if language_code:
            original_message = reaction.message.content
            original_author = reaction.message.author

            try:
                # Translate the message
                translated_text = self.translator.translate(
                    original_message, dest=language_code
                ).text

                # Create an embed with the translation
                embed = discord.Embed(
                    description=translated_text,
                    color=discord.Color.blue(),
                )
                
                # Send the embed in the same channel
                await reaction.message.channel.send(embed=embed)

            except Exception as e:
                print(f"Translation error: {e}")
                await reaction.message.channel.send(
                    "An error occurred while translating the message."
                )


def setup(bot):
    bot.add_cog(Translator(bot))
