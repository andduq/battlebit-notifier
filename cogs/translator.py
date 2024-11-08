import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidPayload, LanguageNotSupportedException


class Translator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Mapping of emoji flags to language codes
        self.flag_to_language = {
            "🇺🇸": "en",
            "🇫🇷": "fr",
            "🇪🇸": "es",
            "🇩🇪": "de",
            "🇮🇹": "it",
            "🇷🇺": "ru",
            "🇨🇳": "zh-CN",
            "🇯🇵": "ja",
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        if not message:
            return

        if message.author.bot:
            return

        emoji = str(payload.emoji)
        language_code = self.flag_to_language.get(emoji)
        if language_code:
            original_message = message.content
            original_author = message.author

            try:
                # Translate the message using deep-translator
                translated_text = GoogleTranslator(
                    source="auto", target=language_code
                ).translate(original_message)

                # Create an embed with the translation            
                embed = discord.Embed(
                    description=translated_text,
                    color=discord.Color.blue(),
                )
                embed.set_author(name=original_author.display_name, icon_url=original_author.avatar.url)
                await channel.send(embed=embed)

            except NotValidPayload:
                await channel.send(f"Invalid payload for translation.")
            except LanguageNotSupportedException:
                await channel.send(f"Language not supported.")
            except Exception as e:
                print(f"Translation error: {e}")
                await channel.send("An error occurred while translating the message. Exception: {e}")
        else:
            await message.remove_reaction(emoji, payload.member)

def setup(bot):
    bot.add_cog(Translator(bot))