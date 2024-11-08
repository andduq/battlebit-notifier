import discord
from discord.ext import commands, tasks
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidPayload, LanguageNotSupportedException
import time

class Translator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emoji_to_language = self.get_language_emoji_mapping()
        self.processed_reactions = {}
        self.reaction_timeout_seconds = 60 * 5 # 5 minutes
        self.cleanup_task.start()

    def get_language_emoji_mapping(self):
        return {
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

    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        current_time = time.time()
        for message_id in list(self.processed_reactions):
            self.processed_reactions[message_id] = {
                emoji: timestamp
                for emoji, timestamp in self.processed_reactions[message_id].items()
                if current_time - timestamp < self.reaction_timeout_seconds
            }
            if not self.processed_reactions[message_id]:
                del self.processed_reactions[message_id]

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
        language_code = self.emoji_to_language.get(emoji)

        if language_code:
            message_id = message.id

            if message_id in self.processed_reactions and emoji in self.processed_reactions[message_id]:
                return

            original_message = message.content
            original_author = message.author

            try:
                translated_text = GoogleTranslator(source="auto", target=language_code).translate(original_message)

                embed = discord.Embed(
                    description=translated_text,
                    color=discord.Color.blue(),
                )
                embed.set_author(name=original_author.display_name, icon_url=original_author.avatar.url)

                await channel.send(embed=embed)

                if message_id not in self.processed_reactions:
                    self.processed_reactions[message_id] = {}
                self.processed_reactions[message_id][emoji] = time.time()

            except LanguageNotSupportedException:
                await channel.send(f"Sorry, the language for `{emoji}` is not supported.")
            except NotValidPayload:
                await channel.send("The message could not be translated. It may be empty or invalid.")
            except Exception as e:
                print(f"Translation error: {e}")
                await channel.send("An unexpected error occurred while translating.")

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(Translator(bot))