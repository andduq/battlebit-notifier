import discord
from discord.ext import commands
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidPayload, LanguageNotSupportedException


class Translator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.flag_to_language = {
            "🇿🇦": "af",  # Afrikaans
            "🇦🇱": "sq",  # Albanian
            "🇪🇹": "am",  # Amharic
            "🇸🇦": "ar",  # Arabic
            "🇦🇲": "hy",  # Armenian
            "🇦🇿": "az",  # Azerbaijani
            "🇧🇾": "be",  # Belarusian
            "🇧🇩": "bn",  # Bengali
            "🇧🇦": "bs",  # Bosnian
            "🇧🇬": "bg",  # Bulgarian
            "🇪🇸": "ca",  # Catalan
            "🇨🇳": "zh-CN",  # Chinese Simplified
            "🇭🇷": "hr",  # Croatian
            "🇨🇿": "cs",  # Czech
            "🇩🇰": "da",  # Danish
            "🇳🇱": "nl",  # Dutch
            "🇺🇸": "en",  # English
            "🇪🇪": "et",  # Estonian
            "🇫🇮": "fi",  # Finnish
            "🇫🇷": "fr",  # French
            "🇩🇪": "de",  # German
            "🇬🇷": "el",  # Greek
            "🇭🇹": "ht",  # Haitian Creole
            "🇮🇱": "iw",  # Hebrew
            "🇮🇳": "hi",  # Hindi
            "🇭🇺": "hu",  # Hungarian
            "🇮🇸": "is",  # Icelandic
            "🇮🇩": "id",  # Indonesian
            "🇮🇪": "ga",  # Irish
            "🇮🇹": "it",  # Italian
            "🇯🇵": "ja",  # Japanese
            "🇰🇿": "kk",  # Kazakh
            "🇰🇷": "ko",  # Korean
            "🇱🇻": "lv",  # Latvian
            "🇱🇹": "lt",  # Lithuanian
            "🇲🇾": "ms",  # Malay
            "🇳🇴": "no",  # Norwegian
            "🇵🇱": "pl",  # Polish
            "🇧🇷": "pt",  # Portuguese
            "🇷🇴": "ro",  # Romanian
            "🇷🇺": "ru",  # Russian
            "🇷🇸": "sr",  # Serbian
            "🇸🇰": "sk",  # Slovak
            "🇸🇮": "sl",  # Slovenian
            "🇪🇸": "es",  # Spanish
            "🇸🇪": "sv",  # Swedish
            "🇹🇭": "th",  # Thai
            "🇹🇷": "tr",  # Turkish
            "🇺🇦": "uk",  # Ukrainian
            "🇵🇰": "ur",  # Urdu
            "🇻🇳": "vi",  # Vietnamese
            "🇿🇦": "zu",  # Zulu
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
                translated_text = GoogleTranslator(
                    source="auto", target=language_code
                ).translate(original_message)

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

def setup(bot):
    bot.add_cog(Translator(bot))