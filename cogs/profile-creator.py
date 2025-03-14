import discord
from discord.ext import commands, tasks
from discord.commands import option
from bot import CustomBot
import logging
from firestore_helper import get_firestore_client, get_storage_bucket
import firebase_admin
from typing import Dict, Any, Tuple, Optional, Literal, List
import json
import os
from google.cloud import storage
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1 import DocumentSnapshot
import re
from discord.ext.commands import has_role
import tempfile
from datetime import timezone 
from datetime import datetime
import asyncio
import aiohttp

log = logging.getLogger("ProfileCreator")

PROFILE_SCHEMA = {
    "bio": str,
    "accent_color": str,
    "twitter_profile_url" : str,
    "youtube_profile_url" : str,
    "twitch_profile_url" : str,
    "join_date": int,  # Unix timestamp
    "membership_type": str,
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
    "join_date": "int",  # Unix timestamp
    "membership_type": "str (Member or Founder)",
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
    "join_date": 1672531200,  # Example: Jan 1, 2023 00:00:00 UTC
    "membership_type": "Member",
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
MAX_BIO_LENGTH = 600
STEAM_ID_PATTERN = r'^\d{17}$'  # Steam ID format validation
COLOR_PATTERN = r'^#[0-9A-Fa-f]{6}$'  # Hex color validation
MEMBERSHIP_TYPES = Literal["Member", "Founder"]
ALLOWED_MEMBERSHIP_TYPES = ["Member", "Founder"]

# Field constraints
STAT_CONSTRAINTS = {
    "kdr": (0, 100),  # min, max
    "kpm": (0, 100),
    "time_played": (0, 1000000),
    "level": (0, 200),
    "prestige": (0, 10),
}

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
STEAM_API_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
BATCH_SIZE = 100  # Steam API spec only allows up to 100 Steam IDs per request

class ProfileCreator(commands.Cog):
    """Cog for managing user profiles including creation, updates, and file uploads."""
    
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.db = get_firestore_client()
        self.bucket = get_storage_bucket()
        self.command_messages = {}  # Track messages by user ID

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("ProfileCreator cog is ready")
        self.steam_profile_monitor.start()

    def cog_unload(self):
        self.steam_profile_monitor.cancel()  # Cleanup task on unload

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

            # Validate join_date
            if "join_date" in data:
                if not isinstance(data["join_date"], int):
                    errors.append("join_date must be an integer (Unix timestamp)")
                elif data["join_date"] < 0:
                    errors.append("join_date cannot be negative")
                elif data["join_date"] > int(datetime.now(timezone.utc).timestamp()):
                    errors.append("join_date cannot be in the future")

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

            # Validate membership_type
            if "membership_type" in data:
                if not isinstance(data["membership_type"], str):
                    errors.append("membership_type must be a string")
                elif data["membership_type"] not in ALLOWED_MEMBERSHIP_TYPES:
                    errors.append(f"membership_type must be one of: {', '.join(ALLOWED_MEMBERSHIP_TYPES)}")

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

    async def _validate_membership_request(self, ctx: discord.ApplicationContext, membership_type: str) -> bool:
        """Validates founder membership requests with admin confirmation."""
        if membership_type != "Founder":
            return True

        # Send confirmation request
        admin_role = discord.utils.get(ctx.guild.roles, name="Admin")
        confirm_msg = await ctx.followup.send(
            f"User {ctx.author.mention} is requesting Founder status. {admin_role.mention} confirmation required.\n"
            "React with ✅ to approve or ❌ to deny.",
            wait=True
        )

        # Add reactions
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, user):
            return (
                user.get_role(discord.utils.get(ctx.guild.roles, name="Admin").id) and
                str(reaction.emoji) in ["✅", "❌"] and
                reaction.message.id == confirm_msg.id
            )

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
            await confirm_msg.delete()
            return str(reaction.emoji) == "✅"
        except asyncio.TimeoutError:
            await confirm_msg.delete()
            await ctx.followup.send("❌ Founder request timed out. Defaulting to Member status.")
            return False

    @commands.guild_only()
    @has_role("Member")
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

            # After validation but before saving
            if "membership_type" in profile_data:
                is_approved = await self._validate_membership_request(ctx, profile_data["membership_type"])
                if not is_approved:
                    profile_data["membership_type"] = "Member"

            # Add metadata
            profile_data.update({
                "steam_id": steam_id,
                "discord_id": ctx.author.id,
                "discord_username": ctx.author.name,
                "banner_url": "",
                "soundtrack_url": "",
                "last_updated": int(datetime.now(timezone.utc).timestamp()),
                "membership_type": profile_data.get("membership_type", "Member"),  # Default to Member
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
    @has_role("Member")
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

            # After validation but before updating
            if "membership_type" in update_data:
                current_type = profile_ref.get("membership_type")
                if current_type is None:
                    current_type = "Member"
                
                if update_data["membership_type"] != current_type:
                    is_approved = await self._validate_membership_request(ctx, update_data["membership_type"])
                    if not is_approved:
                        update_data["membership_type"] = current_type

            # Update profile
            update_data['last_updated'] = int(datetime.now(timezone.utc).timestamp())
            profile_ref.reference.update(update_data)

            # Update discord username in case it changed
            if "discord_username" in update_data:
                profile_ref.reference.update({"discord_username": update_data["discord_username"]})
            else:
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
    @has_role("Member")
    @commands.slash_command(name="update-banner", description="Update profile banner")
    async def update_banner(self, ctx: discord.ApplicationContext) -> None:
        """Updates the profile banner for a user."""
        await ctx.defer()
        await self._handle_file_upload(ctx, "banner", ALLOWED_IMAGE_TYPES)

    @commands.guild_only()
    @has_role("Member")
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

            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                # Download the file
                await file.save(temp_file.name)
                
                # Upload to Storage bucket with consistent naming
                steam_id = profile_ref.get('steam_id')
                blob_path = f"{steam_id}/{file_type}{ext}"
                blob = self.bucket.blob(blob_path)
                
                # Upload the file directly, overwriting if it exists
                blob.upload_from_filename(temp_file.name)
                blob.content_type = file.content_type  # Preserve the content type
                blob.make_public()

            # Clean up temporary file
            os.unlink(temp_file.name)

            # Update profile with new URL
            url = blob.public_url
            profile_ref.reference.update({
                f"{file_type}_url": url,
                "last_updated": int(datetime.now(timezone.utc).timestamp())
            })

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
 
    @commands.guild_only()
    @has_role("Admin")
    @commands.slash_command(
        name="admin-create-profile",
        description="Admin command to create a profile for a non-Discord user"
    )
    @option("steam_id", "Steam ID (17 digits)", required=True, type=str)
    async def admin_create_profile(
        self, ctx: discord.ApplicationContext, steam_id: str
    ) -> None:
        """Creates a profile for a non-Discord user (Admin only)."""
        await ctx.defer()

        if not self.validate_steam_id(steam_id):
            await ctx.followup.send("❌ Invalid Steam ID format. Must be 17 digits.")
            return

        if self.profile_exists(steam_id):
            await ctx.followup.send("❌ Profile already exists with that Steam ID.")
            return

        prompt_msg = await ctx.send("Please upload the profile JSON file with the following format:\n```json\n" + 
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

            # Add metadata (without discord_id)
            profile_data.update({
                "steam_id": steam_id,
                "discord_id": "",
                "discord_username": "",
                "banner_url": "",
                "soundtrack_url": "",
                "last_updated": int(datetime.now(timezone.utc).timestamp()),
                "membership_type": profile_data.get("membership_type", "Member"),
            })

            # Save to Firestore
            self.db.collection(COLLECTION_NAME).document(steam_id).set(profile_data)

            await self._cleanup_command_messages(ctx)
            await ctx.followup.send(f"✅ Profile created successfully for user {steam_id}!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error creating profile: {e}")
            await ctx.followup.send("❌ An error occurred while creating the profile.")

    @commands.guild_only()
    @has_role("Admin")
    @commands.slash_command(
        name="admin-update-profile",
        description="Admin command to update a profile for a non-Discord user"
    )
    @option("steam_id", "Steam ID to update", required=True, type=str)
    async def admin_update_profile(self, ctx: discord.ApplicationContext, steam_id: str) -> None:
        """Updates a profile for a non-Discord user (Admin only)."""
        await ctx.defer()

        # Get profile by Steam ID
        profile_ref = self.db.collection(COLLECTION_NAME).document(steam_id).get()
        if not profile_ref.exists:
            await ctx.followup.send("❌ Profile not found.")
            return

        prompt_msg = await ctx.send("Please upload the updated profile JSON file.")
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

            update_data['last_updated'] = int(datetime.now(timezone.utc).timestamp())

            # Update profile
            profile_ref.reference.update(update_data)

            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("✅ Profile updated successfully!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error updating profile: {e}")
            await ctx.followup.send("❌ An error occurred while updating the profile.")

    @commands.guild_only()
    @has_role("Admin")
    @commands.slash_command(
        name="admin-update-banner",
        description="Admin command to update banner for any profile using Steam ID"
    )
    @option("steam_id", "Steam ID of the profile", required=True, type=str)
    async def admin_update_banner(self, ctx: discord.ApplicationContext, steam_id: str) -> None:
        """Updates the banner for any profile (Admin only)."""
        await ctx.defer()
        await self._handle_admin_file_upload(ctx, steam_id, "banner", ALLOWED_IMAGE_TYPES)

    @commands.guild_only()
    @has_role("Admin")
    @commands.slash_command(
        name="admin-update-soundtrack",
        description="Admin command to update soundtrack for any profile using Steam ID"
    )
    @option("steam_id", "Steam ID of the profile", required=True, type=str)
    async def admin_update_soundtrack(self, ctx: discord.ApplicationContext, steam_id: str) -> None:
        """Updates the soundtrack for any profile (Admin only)."""
        await ctx.defer()
        await self._handle_admin_file_upload(ctx, steam_id, "soundtrack", ALLOWED_AUDIO_TYPES)

    async def _handle_admin_file_upload(self, ctx: discord.ApplicationContext, steam_id: str, file_type: str, allowed_types: list) -> None:
        """Handles admin file uploads for profile updates using Steam ID."""
        if not self.validate_steam_id(steam_id):
            await ctx.followup.send("❌ Invalid Steam ID format. Must be 17 digits.")
            return

        profile_ref = self.db.collection(COLLECTION_NAME).document(steam_id).get()
        if not profile_ref.exists:
            await ctx.followup.send("❌ Profile not found.")
            return

        prompt_msg = await ctx.send(f"Please upload the {file_type} file:")
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

            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
                # Download the file
                await file.save(temp_file.name)
                
                # Upload to Storage bucket with consistent naming
                blob_path = f"{steam_id}/{file_type}{ext}"
                blob = self.bucket.blob(blob_path)
                
                # Upload the file directly, overwriting if it exists
                blob.upload_from_filename(temp_file.name)
                blob.content_type = file.content_type  # Preserve the content type
                blob.make_public()

            # Clean up temporary file
            os.unlink(temp_file.name)

            # Update profile with new URL
            profile_ref.reference.update({
                f"{file_type}_url": blob.public_url,
                "last_updated": int(datetime.now(timezone.utc).timestamp())
            })

            # Clean up messages and send final confirmation
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send(f"✅ {file_type.capitalize()} updated successfully for Steam ID: {steam_id}!")

        except TimeoutError:
            await self._cleanup_command_messages(ctx)
            await ctx.followup.send("❌ Upload timed out.")
        except Exception as e:
            await self._cleanup_command_messages(ctx)
            log.error(f"Error handling file upload: {e}")
            await ctx.followup.send("❌ An error occurred while processing your file.")

    async def fetch_steam_profiles(self, steam_ids: List[str]) -> Dict[str, str]:
        """Fetches Steam profiles for given Steam IDs."""
        try:
            params = {
                "key": STEAM_API_KEY,
                "steamids": ",".join(steam_ids)
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(STEAM_API_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        players = data.get("response", {}).get("players", [])
                        return {
                            str(player["steamid"]): player["personaname"]
                            for player in players
                        }
            return {}
        except Exception as e:
            log.error(f"Error fetching Steam profiles: {e}")
            return {}

    async def update_profile_aliases(self, steam_id: str, current_username: str, 
                                   profile_ref: DocumentSnapshot) -> None:
        """Updates profile aliases if username has changed."""
        try:
            profile_data = profile_ref.to_dict()
            stored_username = profile_data.get("steam_username")
            
            # Initialize aliases array if it doesn't exist
            if "aliases" not in profile_data:
                profile_data["aliases"] = []

            # If username has changed, add to aliases
            if stored_username and stored_username != current_username:
                alias_entry = {
                    "steam_username": stored_username,
                    "date": int(datetime.now(timezone.utc).timestamp())
                }
                profile_data["aliases"].append(alias_entry)
                
                # Update profile with new username and aliases
                profile_ref.reference.update({
                    "steam_username": current_username,
                    "aliases": profile_data["aliases"],
                    "date": int(datetime.now(timezone.utc).timestamp())
                })
                log.info(f"Updated aliases for Steam ID {steam_id}")
            elif not stored_username:
                # If no username stored, just set it
                profile_ref.reference.update({
                    "steam_username": current_username,
                    "date": int(datetime.now(timezone.utc).timestamp())
                })

        except Exception as e:
            log.error(f"Error updating aliases for Steam ID {steam_id}: {e}")

    @tasks.loop(seconds=3600)
    async def steam_profile_monitor(self) -> None:
        """Monitors Steam profiles for username changes."""
        try:
            log.info("Checking Steam profiles for name changes...")
            profiles = self.db.collection(COLLECTION_NAME).get()
            steam_ids = [profile.id for profile in profiles]

            for i in range(0, len(steam_ids), BATCH_SIZE):
                batch_ids = steam_ids[i:i + BATCH_SIZE]
                steam_data = await self.fetch_steam_profiles(batch_ids)

                for steam_id, username in steam_data.items():
                    profile_ref = next(
                        (p for p in profiles if p.id == steam_id), None
                    )
                    if profile_ref:
                        await self.update_profile_aliases(steam_id, username, profile_ref)

        except Exception as e:
            log.error(f"Error in Steam profile monitor: {e}")

    @steam_profile_monitor.before_loop
    async def before_steam_profile_monitor(self):
        """Wait for bot to be ready before starting the task."""
        await self.bot.wait_until_ready()

def setup(bot: CustomBot):
    bot.add_cog(ProfileCreator(bot))