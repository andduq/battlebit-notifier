import discord
from discord.ext import commands
from discord.commands import option
from bot import CustomBot
import logging
from firestore_helper import get_firestore_client, get_storage_bucket
import firebase_admin
from typing import Dict, Any, Tuple, Optional
import json
import os
from google.cloud import storage
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import DocumentSnapshot
import re

log = logging.getLogger("ProfileCreator")

PROFILE_SCHEMA = {
    "bio": str,
    "accent_color": str,
    "twitter_profile_url" : str,
    "youtube_profile_url" : str,
    "twitch_profile_url" : str,
    "stats": {
        "m200_kills": int,
        "l96_kills": int,
        "rem700_kills": int,
        "sv98_kills": int,
        "msr_kills": int,
        "ssg69_kills": int,
        "total_kills": int,
        "kdr": float | int,
        "kpm": float | int,
        "time_played": int | float,
        "score": int,
        "prestige": int,
        "level": int,
    }
}
PROFILE_SCHEMA_STR = {
    "bio": "str",
    "accent_color": "str",
    "twitter_profile_url" : "str",
    "youtube_profile_url" : "str",
    "twitch_profile_url" : "str",
    "stats": {
        "m200_kills": "int",
        "l96_kills": "int",
        "rem700_kills": "int",
        "sv98_kills": "int",
        "msr_kills": "int",
        "ssg69_kills": "int",
        "total_kills": "int",
        "kdr": "float | int",
        "kpm": "float | int",
        "time_played": "int | float",
        "score": "int",
        "prestige": "int",
        "level": "int",
    }
}

PROFILE_EXAMPLE = {
    "bio": "Super awesome bio",
    "accent_color": "#FF0000",
    "twitter_profile_url" : "https://twitter.com/username or nothing",
    "youtube_profile_url" : "https://www.youtube.com/channel/username or nothing",
    "twitch_profile_url" : "https://www.twitch.tv/username or nothing",
    "stats": {
        "m200_kills": 100,
        "l96_kills": 50,
        "rem700_kills": 25,
        "sv98_kills": 10,
        "msr_kills": 5,
        "ssg69_kills": 2,
        "total_kills": 192,
        "kdr": 2.5,
        "kpm": 1.4,
        "time_played": 1000,
        "score": 150000000,
        "prestige": 6,
        "level": 200,
    }
}

ALLOWED_IMAGE_TYPES = ['.png', '.jpg', '.jpeg', '.gif']
ALLOWED_AUDIO_TYPES = ['.mp3', '.wav']

# Constants
TIMEOUT_SECONDS = 300
COLLECTION_NAME = "profiles"
MAX_BIO_LENGTH = 500
STEAM_ID_PATTERN = r'^\d{17}$'  # Steam ID format validation
COLOR_PATTERN = r'^#[0-9A-Fa-f]{6}$'  # Hex color validation

# Field constraints
STAT_CONSTRAINTS = {
    "kdr": (0, 100),  # min, max
    "kpm": (0, 100),
    "time_played": (0, 1000000),
    "level": (0, 200),
    "prestige": (0, 10),
}

class ProfileCreator(commands.Cog):
    """Cog for managing user profiles including creation, updates, and file uploads."""
    
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.db = get_firestore_client()
        self.bucket = get_storage_bucket()
        self.command_messages = {}  # Track messages by user ID

    async def _track_message(self, ctx: discord.ApplicationContext, message: discord.Message) -> None:
        """Tracks a message related to a command interaction."""
        if ctx.author.id not in self.command_messages:
            self.command_messages[ctx.author.id] = []
        self.command_messages[ctx.author.id].append(message)

    async def _cleanup_command_messages(self, ctx: discord.ApplicationContext) -> None:
        """Cleans up all tracked messages for a command interaction."""
        if ctx.author.id in self.command_messages:
            for message in self.command_messages[ctx.author.id]:
                try:
                    await message.delete()
                except Exception as e:
                    log.error(f"Error deleting message: {e}")
            del self.command_messages[ctx.author.id]

    def _validate_profile_data(self, data: Dict[str, Any]) -> Tuple[bool, list[str]]:
        """Validates profile data against schema and constraints."""
        errors = []
        try:
            if not isinstance(data, dict):
                return False, ["Invalid data format"]

            # Validate bio
            if "bio" in data:
                if not isinstance(data["bio"], str):
                    errors.append("bio must be a string")
                elif len(data["bio"]) > MAX_BIO_LENGTH:
                    errors.append(f"bio must be less than {MAX_BIO_LENGTH} characters")

            # Validate accent_color
            if "accent_color" in data:
                if not isinstance(data["accent_color"], str):
                    errors.append("accent_color must be a string")
                elif not re.match(COLOR_PATTERN, data["accent_color"]):
                    errors.append("accent_color must be a valid hex color (e.g., #FF0000)")

            # Validate stats
            if "stats" in data:
                if not isinstance(data["stats"], dict):
                    errors.append("stats must be a dictionary")
                else:
                    for field, value in data["stats"].items():
                        if field not in PROFILE_SCHEMA["stats"]:
                            errors.append(f"Unknown stat field: {field}")
                            continue

                        # Type validation
                        if not isinstance(value, PROFILE_SCHEMA["stats"][field]):
                            errors.append(f"{field} must be of type {PROFILE_SCHEMA_STR['stats'][field]}")

                        # Range validation (inclusive)
                        if field in STAT_CONSTRAINTS:
                            min_val, max_val = STAT_CONSTRAINTS[field]
                            if value < min_val or value > max_val:
                                errors.append(f"{field} must be between {min_val} and {max_val} (inclusive)")


            return not errors, errors

        except Exception as e:
            log.error(f"Validation error: {e}")
            return False, [str(e)]

    async def get_user_profile(self, discord_id: int) -> Optional[DocumentSnapshot]:
        """Gets a user's profile from Firestore."""
        try:
            profile_ref = self.db.collection(COLLECTION_NAME).where(
                filter=FieldFilter("discord_id", "==", discord_id)
            ).get()
            return profile_ref[0] if profile_ref else None
        except Exception as e:
            log.error(f"Error getting user profile: {e}")
            return None

    def validate_steam_id(self, steam_id: str) -> bool:
        """Validates Steam ID format."""
        return bool(re.match(STEAM_ID_PATTERN, steam_id))

    @commands.guild_only()
    @commands.slash_command(name="create-profile", description="Create a new profile using a JSON file")
    @option("steam_id", "Your Steam ID (17 digits)", required=True, type=str)
    async def create_profile(self, ctx: discord.ApplicationContext, steam_id: str) -> None:
        """Creates a new profile for a user."""
        await ctx.defer()

        if not self.validate_steam_id(steam_id):
            await ctx.followup.send("❌ Invalid Steam ID format. Must be 17 digits.")
            return

        if self.profile_exists(steam_id):
            await ctx.followup.send("❌ Profile already exists with that Steam ID.")
            return

        prompt_msg = await ctx.send("Please upload your profile JSON file with the following format:\n```json\n" + 
                      json.dumps(PROFILE_EXAMPLE, indent=2) + "\n```")
        await self._track_message(ctx, prompt_msg)

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=TIMEOUT_SECONDS,
                check=lambda m: m.author == ctx.author and m.attachments
            )
            await self._track_message(ctx, msg)

            if not msg.attachments or not msg.attachments[0].filename.endswith('.json'):
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Please upload a valid JSON file.")
                return

            # Read and validate JSON
            file_content = await msg.attachments[0].read()
            try:
                profile_data = json.loads(file_content)
            except json.JSONDecodeError:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Invalid JSON format.")
                return

            validate_result = self._validate_profile_data(profile_data)
            if not validate_result[0]:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Invalid profile data structure: " + ", ".join(validate_result[1]))
                return

            # Add metadata
            profile_data.update({
                "steam_id": steam_id,
                "discord_id": ctx.author.id,
                "discord_ursername": ctx.author.name,
                "banner_url": "",
                "soundtrack_url": ""
            })

            # Save to Firestore
            self.db.collection(COLLECTION_NAME).document(steam_id).set(profile_data)

            # Clean up messages and send final confirmation
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("✅ Profile created successfully!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error creating profile: {e}")
            await ctx.followup.send("❌ An error occurred while creating your profile.")

    @commands.guild_only()
    @commands.slash_command(name="update-profile", description="Update profile using a JSON file")
    async def update_profile(self, ctx: discord.ApplicationContext) -> None:
        """Updates an existing profile for a user."""
        await ctx.defer()

        profile_ref = await self.get_user_profile(ctx.author.id)
        if not profile_ref:
            await ctx.followup.send("❌ Profile not found.")
            return

        prompt_msg = await ctx.send("Please upload your updated profile JSON file.")
        await self._track_message(ctx, prompt_msg)

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=TIMEOUT_SECONDS,
                check=lambda m: m.author == ctx.author and m.attachments
            )
            await self._track_message(ctx, msg)

            if not msg.attachments or not msg.attachments[0].filename.endswith('.json'):
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Please upload a valid JSON file.")
                return

            file_content = await msg.attachments[0].read()
            try:
                update_data = json.loads(file_content)
            except json.JSONDecodeError:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Invalid JSON format.")
                return

            validate_result = self._validate_profile_data(update_data)
            if not validate_result[0]:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ Invalid profile data structure: " + ", ".join(validate_result[1]))
                return

            # Update profile
            profile_ref.reference.update(update_data)

            # Update discord username in case it changed
            profile_ref.reference.update({"discord_username": ctx.author.name})

            # Clean up messages and send final confirmation
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("✅ Profile updated successfully!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error updating profile: {e}")
            await ctx.followup.send("❌ An error occurred while updating your profile.")

    @commands.guild_only()
    @commands.slash_command(name="update-banner", description="Update profile banner")
    async def update_banner(self, ctx: discord.ApplicationContext) -> None:
        """Updates the profile banner for a user."""
        await ctx.defer()
        await self._handle_file_upload(ctx, "banner", ALLOWED_IMAGE_TYPES)

    @commands.guild_only()
    @commands.slash_command(name="update-soundtrack", description="Update profile soundtrack")
    async def update_soundtrack(self, ctx: discord.ApplicationContext) -> None:
        """Updates the profile soundtrack for a user."""
        await ctx.defer()
        await self._handle_file_upload(ctx, "soundtrack", ALLOWED_AUDIO_TYPES)

    async def _handle_file_upload(self, ctx: discord.ApplicationContext, file_type: str, allowed_types: list) -> None:
        """Handles file uploads for profile updates."""
        profile_ref = await self.get_user_profile(ctx.author.id)
        if not profile_ref:
            await ctx.followup.send("❌ Profile not found.")
            return

        prompt_msg = await ctx.send(f"Please upload your {file_type} file:")
        await self._track_message(ctx, prompt_msg)

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=TIMEOUT_SECONDS,
                check=lambda m: m.author == ctx.author and m.attachments
            )
            await self._track_message(ctx, msg)

            if not msg.attachments:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send("❌ No file attached.")
                return

            file = msg.attachments[0]
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in allowed_types:
                await self._cleanup_command_messages(ctx)
                await ctx.followup.send(f"❌ Invalid file type. Allowed types: {', '.join(allowed_types)}")
                return

            # Upload to Storage bucket with consistent naming
            steam_id = profile_ref.get('steam_id')
            blob_path = f"{steam_id}/{file_type}{ext}"
            
            # Delete old file if it exists
            for old_ext in allowed_types:
                old_blob = self.bucket.blob(f"{steam_id}/{file_type}{old_ext}")
                if old_blob.exists():
                    old_blob.delete()
            
            # Upload new file
            blob = self.bucket.blob(blob_path)
            file_data = await file.read()
            blob.upload_from_string(file_data)
            blob.make_public()

            # Update profile with new URL
            url = blob.public_url
            profile_ref.reference.update({f"{file_type}_url": url})

            # Clean up messages and send final confirmation
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send(f"✅ {file_type.capitalize()} updated successfully!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error handling file upload: {e}")
            await ctx.followup.send("❌ An error occurred while processing your file.")

    def profile_exists(self, steam_id: str) -> bool:
        """Checks if a profile exists for a given Steam ID."""
        return bool(self.db.collection(COLLECTION_NAME).where(filter=FieldFilter("steam_id", "==", steam_id)).get())
    
def setup(bot: CustomBot):
    bot.add_cog(ProfileCreator(bot))