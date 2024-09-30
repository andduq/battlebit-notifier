import discord

class Filter:
    def __init__(
        self,
        min_players: int | None,
        max_players: int | None,
        region: str | None,
        map: str | None,
        game_mode: str | None,
    ):
        self.min_players = min_players
        self.max_players = max_players
        self.region = region
        self.map = map
        self.game_mode = game_mode

    def apply(self, server) -> bool:
        conditions = []
        if self.min_players is not None:
            conditions.append(int(server["Players"]) >= self.min_players)
        if self.max_players is not None:
            conditions.append(int(server["MaxPlayers"]) >= self.max_players)
        if self.region is not None:
            conditions.append(server["Region"] == self.region)
        if self.map is not None:
            conditions.append(server["Map"] == self.map)
        if self.game_mode is not None:
            conditions.append(server["Gamemode"] == self.game_mode)
        return all(conditions)

    def __str__(self) -> str:
        map = self.map if self.map is not None else "Any"
        region = self.region if self.region is not None else "Any"
        min_players = self.min_players if self.min_players is not None else "Any"
        max_players = self.max_players if self.max_players is not None else "Any"
        game_mode = self.game_mode if self.game_mode is not None else "Any"
        return f"Map: {map}, Region: {region}, Min players: {min_players}, Max players: {max_players}, Game mode: {game_mode}"

    def get_embed(self) -> discord.Embed:
        filter_embed = discord.Embed(title="Filter", color=discord.Color.blue())
        map = self.map if self.map is not None else "Any"
        region = self.region if self.region is not None else "Any"
        min_players = self.min_players if self.min_players is not None else "Any"
        max_players = self.max_players if self.max_players is not None else "Any"
        game_mode = self.game_mode if self.game_mode is not None else "Any"
        filter_embed.add_field(
            name="Filters that are currently applied",
            value=f"**Region**: {region}\n**Map**: {map}\n**Min players**: {min_players}\n**Max players**: {max_players}\n**Gamemode**: {game_mode}",
            inline=False,
        )
        return filter_embed
    
    def to_json(self) -> dict:
        return {
            "map": self.map,
            "region": self.region,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "game_mode": self.game_mode
        }
    
    @staticmethod
    def from_json(json):
        return Filter(
            json["min_players"],
            json["max_players"],
            json["region"],
            json["map"],
            json["game_mode"]
        )
