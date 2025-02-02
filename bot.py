# region Imports
import sb_blockchain
import threading
import subprocess
import signal
import asyncio
import json
import pytz
import random
import math
from time import sleep, time
from datetime import datetime
from discord import (Guild, Intents, Interaction, Member, Message, Client,
                     Emoji, PartialEmoji, Role, User, TextChannel, app_commands,
                     utils)
from discord.ui import View, Button
from discord.enums import ButtonStyle
from discord.ext import commands
from discord.raw_models import RawReactionActionEvent
from os import environ as os_environ, getenv, makedirs
from os.path import exists
from dotenv import load_dotenv
from hashlib import sha256
from sys import exit as sys_exit
from sympy import symbols, Expr, Add, Mul, Float, Integer, Rational, simplify
from typing import Dict, List, LiteralString, NoReturn, TextIO, cast, NamedTuple
# endregion

# region Named tuples


class StartingBonusMessage(NamedTuple):
    message_id: int
    invoker_id: int
    invoker_name: str
# endregion


# Intents and bot setup
intents: Intents = Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot("!", intents=intents)
client = Client(intents=intents)
# Load .env file for the bot DISCORD_TOKEN
load_dotenv()
DISCORD_TOKEN: str | None = getenv('DISCORD_TOKEN')
channel_checkpoint_limit: int = 3
guild_ids: List[int] = []
starting_bonus_messages_waiting: Dict[int, StartingBonusMessage] = {}
# endregion

# region Checkpoints


class ChannelCheckpoints:
    def __init__(self,
                 guild_name: str,
                 guild_id: int,
                 channel_name: str,
                 channel_id: int,
                 number: int = 10) -> None:
        self.number: int = number
        # TODO Add a file in directories that state the names of guilds/channels
        self.guild_name: str = guild_name
        self.guild_id: int = guild_id
        self.channel_name: str = channel_name
        self.channel_id: int = channel_id
        self.directory: str = (f"data/checkpoints/guilds/{self.guild_id}"
                               f"/channels/{self.channel_id}")
        self.file_name: str = f"{self.directory}/channel_checkpoints.json"
        self.entry_count: int = self.count_lines()
        self.last_message_ids: List[Dict[str, int]] | None = self.load()

    def count_lines(self) -> int:
        if not exists(self.file_name):
            return 0

        with open(self.file_name, "r") as file:
            count: int = sum(1 for _ in file)
            return count

    def create(self) -> None:
        # Create missing directories
        directories: str = self.file_name[:self.file_name.rfind("/")]
        for i, directory in enumerate(directories.split("/")):
            path: str = "/".join(directories.split("/")[:i+1])
            if not exists(directory):
                makedirs(path, exist_ok=True)
            # Write the guild name and channel name to files in the id
            # directories, so that bot maintainers can identify the guilds and
            # channels
            # Channel names can change, but the IDs will not
            if directory.isdigit() and int(directory) == self.guild_id:
                name_file_name: str = f"{path}/guild_name.json"
                with open(name_file_name, "w") as file:
                    file.write(json.dumps({"guild_name": self.guild_name}))
                    pass
            elif directory.isdigit() and int(directory) == self.channel_id:
                name_file_name: str = f"{path}/channel_name.json"
                with open(name_file_name, "w") as file:
                    file.write(json.dumps({"channel_name": self.channel_name}))
                    pass

        print(f"Creating checkpoints file: '{self.file_name}'")
        with open(self.file_name, "w"):
            pass

    def save(self, message_id: int) -> None:
        if not exists(self.file_name):
            self.create()

        # print(f"Saving checkpoint: {message_id}")
        self.entry_count = self.count_lines()
        with open(self.file_name, "a") as file:
            if self.entry_count == 0:
                file.write(json.dumps({"last_message_id": message_id}))
            else:
                file.write("\n" + json.dumps({"last_message_id": message_id}))
        self.entry_count += 1

        while self.entry_count > self.number:
            self.remove_first_line()
            self.entry_count -= 1

    def remove_first_line(self) -> None:
        with open(self.file_name, "r") as file:
            lines: List[str] = file.readlines()
        with open(self.file_name, "w") as file:
            file.writelines(lines[1:])

    def load(self) -> List[Dict[str, int]] | None:
        if not exists(self.file_name):
            return None

        with open(self.file_name, "r") as file:
            checkpoints: List[Dict[str, int]] | None = []
            # print("Loading checkpoints...")
            for line in file:
                checkpoint: Dict[str, int] = (
                    {k: int(v) for k, v in json.loads(line).items()})
                # print(f"checkpoint: {checkpoint}")
                checkpoints.append(checkpoint)
                return checkpoints
# endregion

# region Log


class Log:
    '''
    The log cannot currently be verified or generated from the blockchain.
    Use a validated transactions file for verification (see
    Blockchain.validate_transactions_file()).
    The log is meant to be a local record of events.
    '''

    def __init__(self,
                 file_name: str = "data/transactions.log",
                 time_zone: str | None = None) -> None:
        self.file_name: str = file_name
        self.time_zone: str | None = time_zone
        timestamp: float = time()
        if time_zone is not None:
            self.log(f"The time zone is set to '{time_zone}'.", timestamp)
        else:
            self.log("The time zone is set to the local time zone.", timestamp)

    def create(self) -> None:
        # Create missing directories
        directories: str = self.file_name[:self.file_name.rfind("/")]
        for _, directory in enumerate(directories.split("/")):
            if not exists(directory):
                makedirs(directory)

        # Create the log file
        with open(self.file_name, "w"):
            pass

    def log(self, line: str, timestamp: float) -> None:
        if self.time_zone is None:
            # Use local time zone
            timestamp_friendly = (
                datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"))
        else:
            # Convert Unix timestamp to datetime object
            timestamp_dt: datetime = (
                datetime.fromtimestamp(timestamp, pytz.utc))

            # Adjust for time zone
            timestamp_dt = (
                timestamp_dt.astimezone(pytz.timezone(self.time_zone)))

            # Format the timestamp
            timestamp_friendly: str = (
                timestamp_dt.strftime("%Y-%m-%d %H:%M:%S"))

        # Create the log file if it doesn't exist
        if not exists(self.file_name):
            self.create()

        with open(self.file_name, "a") as f:
            timestamped_line: str = f"{timestamp_friendly}: {line}"
            print(timestamped_line)
            f.write(f"{timestamped_line}\n")


# endregion

# region Bot config
class BotConfiguration:
    def __init__(self, file_name: str = "data/bot_configuration.json") -> None:
        self.file_name: str = file_name
        self.configuration: Dict[str, str | Dict[str, Dict[str, int]]] = (
            self.read())
        self.coin: str = str(self.configuration["coin"])
        self.Coin: str = str(self.configuration["Coin"])
        self.coins: str = str(self.configuration["coins"])
        self.Coins: str = str(self.configuration["Coins"])
        self.coin_emoji_id: int = int(str(self.configuration["COIN_EMOJI_ID"]))
        print(f"configuration: {self.configuration}")
        if self.coin_emoji_id == 0:
            print("WARNING: COIN_EMOJI_ID has not set "
                  "in bot_configuration.json nor "
                  "in the environment variables.")
        self.administrator_id: int = int(
            str(self.configuration["ADMINISTRATOR_ID"]))
        self.casino_house_id: int = int(
            str(self.configuration["CASINO_HOUSE_ID"]))
        if self.administrator_id == 0:
            print("WARNING: ADMINISTRATOR_ID has not set "
                  "in bot_configuration.json nor "
                  "in the environment variables.")

    def create(self) -> None:
        # Create missing directories
        directories: str = self.file_name[:self.file_name.rfind("/")]
        for directory in directories.split("/"):
            if not exists(directory):
                makedirs(directory)

        # Create the configuration file
        # Default configuration
        configuration: Dict[str, str | Dict[str, Dict[str, int]]] = {
            "coin": "coin",
            "Coin": "Coin",
            "coins": "coins",
            "Coins": "Coins",
            "COIN_EMOJI_ID": "0",
            "CASINO_HOUSE_ID": "0",
            "ADMINISTRATOR_ID": "0"
        }
        # Save the configuration to the file
        with open(self.file_name, "w") as file:
            file.write(json.dumps(configuration))

    def read(self) -> Dict[str, str | Dict[str, Dict[str, int]]]:
        if not exists(self.file_name):
            self.create()

        with open(self.file_name, "r") as file:
            configuration: Dict[str, str | Dict[str, Dict[str, int]]] = (
                json.loads(file.read()))
            # Override the configuration with environment variables
            env_vars: Dict[str, str] = {
                "coin": "coin",
                "Coin": "Coin",
                "coins": "coins",
                "Coins": "Coins",
                "COIN_EMOJI_ID": "COIN_EMOJI_ID",
                "CASINO_HOUSE_ID": "CASINO_HOUSE_ID",
            }
            # TODO add reels env vars

            for env_var, config_key in env_vars.items():
                if os_environ.get(env_var):
                    configuration[config_key] = os_environ.get(env_var, "")

            return configuration


# endregion

# region Slot machine
class SlotMachine:
    def __init__(self, file_name: str = "data/slot_machine.json") -> None:
        self.file_name: str = file_name
        self.configuration: (
            Dict[str,
                 Dict[str, Dict[str, int | float]] | Dict[str, int] | int]) = (
                self.load_config())
        self._reels: Dict[str, Dict[str, int]] = self.load_reels()
        # self.emoji_ids: Dict[str, int] = cast(Dict[str, int], self.configuration["emoji_ids"])
        self._probabilities: Dict[str, float] = (
            self.calculate_all_probabilities())
        self._jackpot: int = self.load_jackpot()

    def load_reels(self) -> Dict[str, Dict[str, int]]:
        # print("Getting reels...")
        self.configuration = self.load_config()
        reels: Dict[str, Dict[str, int]] = (
            cast(Dict[str, Dict[str, int]], self.configuration["reels"]))
        return reels

    @property
    def reels(self) -> Dict[str, Dict[str, int]]:
        return self._reels

    @reels.setter
    def reels(self, value: Dict[str, Dict[str, int]]) -> None:
        self._reels = value
        self.configuration["reels"] = (
            cast(Dict[str, Dict[str, int | float]], self._reels))
        self.save_config()

    @property
    def probabilities(self) -> Dict[str, float]:
        return self.calculate_all_probabilities()
    
    @property
    def jackpot(self) -> int:
        return self._jackpot
    
    @jackpot.setter
    def jackpot(self, value: int) -> None:
        self._jackpot = value
        self.configuration["jackpot_amount"] = self._jackpot
        self.save_config()

    def load_jackpot(self) -> int:
        self.configuration = self.load_config()
        awards: Dict[str, Dict[str, int | float]] = cast(Dict[str, Dict[str, int | float]], self.configuration["awards"])
        jackpot_seed: int = cast(int, awards["jackpot"]["coin_profit"])
        jackpot_size: int = cast(int, awards["jackpot"]["coin_profit"])
        if jackpot_size < jackpot_seed:
            jackpot: int = jackpot_seed
        else:
            jackpot: int = jackpot_size
        return jackpot

    def create_config(self) -> None:
        print("Creating template slot machine configuration file...")
        # Create missing directories
        directories: str = self.file_name[:self.file_name.rfind("/")]
        makedirs(directories, exist_ok=True)

        # Create the configuration file
        # Default configuration
        configuration: Dict[
            str,
            Dict[str, Dict[str, int | str | float]] |
            Dict[str, int] |
            int |
            float
        ] = {
            "awards": {
                "lose_wager": {
                    "emoji_id": 0,
                    "emoji_name": "",
                    "coin_profit": 0,
                    "wager_multiplier": -1.0
                },
                "small_win": {
                    "emoji_id": 0,
                    "emoji_name": "",
                    "coin_profit": 1,
                    "wager_multiplier": 1.0
                },
                "medium_win": {
                    "emoji_id": 0,
                    "emoji_name": "",
                    "coin_profit": 0,
                    "wager_multiplier": 5.0
                },
                "high_win": {
                    "emoji_id": 0,
                    "emoji_name": "",
                    "coin_profit": 0,
                    "wager_multiplier": 500.0
                },
                "jackpot": {
                    "emoji_id": 0,
                    "emoji_name": "",
                    "coin_profit": 2000,
                    "wager_multiplier": 1.0
                }
            },
            "reels": {
                "1": {
                    "lose_wager": 1,
                    "small_win": 3,
                    "medium_win": 7,
                    "high_win": 2,
                    "jackpot": 1
                },
                "2": {
                    "lose_wager": 1,
                    "small_win": 3,
                    "medium_win": 7,
                    "high_win": 2,
                    "jackpot": 1
                },
                "3": {
                    "lose_wager": 1,
                    "small_win": 3,
                    "medium_win": 7,
                    "high_win": 2,
                    "jackpot": 1
                }
            },
            "jackpot_amount": 0
        }
        # Save the configuration to the file
        with open(self.file_name, "w") as file:
            file.write(json.dumps(configuration))
        print("Template slot machine configuration file created.")

    def load_config(self) -> (
            Dict[
                str, Dict[str, Dict[str, int | float]] | Dict[str, int] | int]):
        if not exists(self.file_name):
            self.create_config()

        with open(self.file_name, "r") as file:
            configuration: (Dict[
                str, Dict[str, Dict[str, int | float]] | Dict[str, int] | int
                ]) = json.loads(file.read())
            return configuration

    def save_config(self) -> None:
        # print("Saving slot machine configuration...")
        with open(self.file_name, "w") as file:
            file.write(json.dumps(self.configuration))
        # print("Slot machine configuration saved.")

    def calculate_probability(self, symbol: str) -> float:
        overall_probability: float = 1.0
        for reel in self.reels:
            number_of_symbol_on_reel: int = self.reels[reel][symbol]
            total_reel_symbols: int = sum(self.reels[reel].values())
            if total_reel_symbols != 0 and number_of_symbol_on_reel != 0:
                probability_for_reel: float = (
                    number_of_symbol_on_reel / total_reel_symbols)
            else:
                probability_for_reel = 0.0
            overall_probability *= probability_for_reel
        return overall_probability

    def calculate_losing_probabilities(self) -> tuple[float, float]:
        print("Calculating chance of losing...")

        # No symbols match
        standard_lose_probability: float = 1.0

        # Either lose_wager symbols match or no symbols match
        any_lose_probability: float = 1.0

        symbols: List[str] = [symbol for symbol in self.reels["1"]]
        for symbol in symbols:
            symbols_match_probability: float = (
                self.calculate_probability(symbol))
            symbols_no_match_probability: float = 1 - symbols_match_probability
            standard_lose_probability *= symbols_no_match_probability
            if symbol != "lose_wager":
                any_lose_probability *= symbols_no_match_probability
        return (any_lose_probability, standard_lose_probability)

    def calculate_all_probabilities(self) -> Dict[str, float]:
        self.reels = self.load_reels()
        probabilities: Dict[str, float] = {}
        for symbol in self.reels["1"]:
            probability: float = self.calculate_probability(symbol)
            probabilities[symbol] = probability
        any_lose_probability: float
        standard_lose_probability: float
        any_lose_probability, standard_lose_probability = (
            self.calculate_losing_probabilities())
        probabilities["standard_lose"] = standard_lose_probability
        probabilities["any_lose"] = any_lose_probability
        probabilities["win"] = 1 - any_lose_probability
        return probabilities

    def count_symbols(self, reel: str | None = None) -> int:
        if reel is None:
            return sum([sum(reel.values()) for reel in self.reels.values()])
        else:
            return sum(self.reels[reel].values())

    # TODO Add TOS
    # TODO Make it don't give back the 1 coin standard fee on win
        # TODO Calculate EV
    def calculate_total_return(self) -> Expr:
        # When the player pays the 1 coin jackpot fee by setting their wager
        # to a value higher than 1, they are eligible for and contributing to 
        # the jackpot.
        # Main game is the game with the jackpot excluded.
        # Main game wager = wager - jackpot_fee
        # Jackpot wager = wager
        # Players keep their main game wager in all win events
        # (including the jackpot fail event, when the player
        # didn't pay the jackpot fee).
        # Players keep the jackpot fee in the jackpot win event.
        self.configuration = self.load_config()
        probabilities: Dict[str, float] = self.calculate_all_probabilities()
        awards: Dict[str, Dict[str, int | float]] = cast(
            Dict[str, Dict[str, int | float]], self.configuration["awards"])
        W: Expr = symbols('W')  # wager
        total_return: Expr = Integer(0)
        event_total_return: Expr = Integer(0)
        for f in range(-1, 1):
            jackpot_fee_int: int = f
            jackpot_fee: Expr = Integer(jackpot_fee_int)
            print(f"Jackpot fee loss: {jackpot_fee_int}")
            for event in awards:
                print(f"----\nEvent: {event}")
                p_event_float: float = probabilities[event]
                if p_event_float == 0.0:
                    continue
                p_event: Expr = Float(p_event_float)
                amount_int: int
                amount: Expr
                wager_multiplier_float: float
                wager_multiplier: Expr
                if event == "standard_lose":
                    if jackpot_fee_int == -1:
                        # If the player pays the 1 coin jackpot fee and loses
                        # He ends up with his wager minus 1 coin minus
                        # the jackpot fee
                        amount = Integer(-1)
                        print(f"Amount: {amount}")
                        wager_multiplier_float = 1.0
                        wager_multiplier = Float(wager_multiplier_float)
                        event_total_return = (
                            Add(Mul(p_event, Add(Mul(W, wager_multiplier), amount, jackpot_fee)))
                        )
                        print(f"Event total return: {event_total_return} "
                              "(probability * "
                              "(wager * multiplier - amount - jackpot_fee))")
                    else:
                        # If the player doesn't pay the 1 coin jackpot fee and
                        # loses
                        # He ends up with his wager minus 1 coin
                        amount = Integer(-1)
                        print(f"Amount: {amount}")
                        wager_multiplier_float = 1.0
                        wager_multiplier = Float(wager_multiplier_float)
                        event_total_return = (
                            Add(Mul(p_event, Add(Mul(W, wager_multiplier), amount)))
                        )
                        print(f"Event total return: {event_total_return} "
                              "(probability * (wager * multiplier - amount))")
                else:
                    amount_int: int = cast(int, awards[event]["coin_profit"])
                    amount = Integer(amount_int)
                    wager_multiplier_float = awards[event]["wager_multiplier"]
                    wager_multiplier = Float(wager_multiplier_float)
                    print(f"Multiplier: {wager_multiplier}")
                    jackpot_average: float
                    p_event = Float(probabilities[event])
                    print(f"Event probability: {p_event}")
                    if event == "jackpot":
                        if f == -1:
                            # If the player pays the 1 coin jackpot fee
                            # and wins the jackpot
                            # He ends up with his wager plus jackpot
                            jackpot_seed_int: int = amount_int
                            jackpot_average: float = (
                                self.calculate_average_jackpot(
                                    seed=jackpot_seed_int))
                            print(f"Jackpot average: {jackpot_average}")
                            jackpot_seed = Integer(jackpot_seed_int)
                            print(f"Jackpot seed: {jackpot_seed}")
                            event_total_return = (
                                Add(Mul(p_event, jackpot_average), W))
                            print(f"Event total return: {event_total_return} "
                                "((probability * jackpot_average) + wager)")
                        else:
                            # If the player doesn't pay the 1 coin jackpot fee
                            # and "wins"
                            jackpot_award_int: int = 0
                            jackpot_award = Integer(jackpot_award_int)
                            event_total_return = (
                                Add(Mul(p_event, jackpot_award)))
                            print(f"Event total return: {event_total_return} "
                                "((probability * 0)")
                    else:
                        print(f"Amount: {amount}")
                        if f == -1:
                            # If the player pays the 1 coin jackpot fee and
                            # wins a non-jackpot award
                            # He ends up with his wager plus award minus
                            # the jackpot fee
                            event_total_return = (
                                Mul(p_event,
                                    Add(
                                        Mul(W, wager_multiplier),
                                        amount,
                                        jackpot_fee)))
                            print(f"Event total return: {event_total_return} "
                                "(probability * "
                                "(wager * multiplier) + amount - jackpot_fee)")
                        else:
                            # If the player doesn't pay the 1 coin jackpot fee and
                            # wins a non-jackpot award
                            # He ends up with his wager plus award
                            event_total_return: Expr = (
                                Mul(
                                    p_event,
                                    Add(Mul(W, wager_multiplier), amount)))
                            print(f"Event total return: {event_total_return} "
                                  "(probability * "
                                  "(wager * multiplier) + amount)")
                total_return = Add(total_return, event_total_return)
        print(f"Total return: {total_return}")
        # total_return_expanded: Expr = cast(Expr, expand(total_return))
        # print(f"Total return expanded: {total_return_expanded}")

        # coefficient = total_return.coeff(W, 1)
        # constant = total_return.coeff(W, 0)
        # print(f"Total return coefficient: {coefficient}")
        # print(f"Total return constant: {constant}")
        return total_return

    def calculate_average_jackpot(self, seed: int) -> float:
        # 1 coin is added to the jackpot for every spin
        contribution_per_spin: int = 1
        probabilities: Dict[str, float] = self.calculate_all_probabilities()
        average_spins_to_win: float = 1 / probabilities["jackpot"]
        jackpot_cycle_growth: float = (
            contribution_per_spin * average_spins_to_win)
        # min + max / 2
        mean_jackpot: float = (0 + jackpot_cycle_growth) / 2
        average_jackpot: float = seed + mean_jackpot
        return average_jackpot

    def calculate_rtp(self, wager: int):
        # TODO Fix problems reported by Pylance
        total_return: Expr = self.calculate_total_return()
        evaluated_total_return: Expr = total_return.subs(symbols('W'), wager)
        rtp = Rational(evaluated_total_return, wager)
        rtp_decimal = rtp.evalf()
        print(f"RTP: {rtp}")
        print(f"RTP decimal: {rtp_decimal}")
        return rtp_decimal

    """ def pull_lever(self):
        symbols_landed = []
        for reel in self.reels:
            symbol = self.stop_reel(reel)
            symbols_landed.append(symbol)
        return symbols_landed """

    def stop_reel(self, reel: str):
        reel_symbols = list(self.reels[reel].keys())
        symbol: str = random.choice(reel_symbols)
        return symbol
    
    def calculate_award_money(self, wager: int, results: Dict[str, Dict[str, str | int | float | PartialEmoji]]) -> tuple[str, str, int]:
        # TODO Figure out if aligned with total_return and RTP calculations
        if not results["1"]["name"] == results["2"]["name"] == results["3"]["name"]:
            return ("standard_lose", "No win", 0)
        
        print("results: ", results)
        award_name: str = cast(str, results["1"]["name"])
        print(f"award_name: {award_name}")
        award_multiplier: float = cast(float, results["1"]["wager_multiplier"])
        award_coin_profit: int = cast(int, results["1"]["coin_profit"])
        print(f"award_multiplier: {award_multiplier}")
        print(f"award_coin_profit: {award_coin_profit}")
        award_name_friendly: str = ""
        win_money: float = 0.0
        win_money_rounded: int = 0
        if award_name == "lose_wager":
            award_name_friendly = "Lose wager"
            return (award_name, award_name_friendly, 0)
        elif award_name == "jackpot":
            if wager == 0:
                award_name = "jackpot_fail"
                award_name_friendly = "No Jackpot"
                win_money_rounded = 0
            else:
                award_name_friendly = "JACKPOT"
                win_money_rounded = self.jackpot
            return (award_name, award_name_friendly, win_money_rounded)
                
        win_money = (
            (wager * award_multiplier) + award_coin_profit)
        win_money_rounded: int = math.floor(win_money)
        # Get rid of ".0"
        award_multiplier_friendly: str
        award_multiplier_floored: int = math.floor(award_multiplier)
        if award_multiplier == award_multiplier_floored:
            award_multiplier_friendly = str(int(award_multiplier))
        else:
            award_multiplier_friendly = str(award_multiplier)
        award_name_friendly += "{}X".format(award_multiplier_friendly)
        if award_coin_profit > 0:
            award_name_friendly = "+{}".format(award_coin_profit)
        return (award_name, award_name_friendly, win_money_rounded)
# endregion

# region UserSaveData


class UserSaveData:
    def __init__(self, user_id: int, user_name: str) -> None:
        self.user_id: int = user_id
        self.user_name: str = user_name
        self.file_name: str = f"data/save_data/{user_id}.json"
        self.starting_bonus_received: bool = False

    def create(self) -> None:
        # Create missing directories
        directories: str = self.file_name[:self.file_name.rfind("/")]
        for i, directory in enumerate(directories.split("/")):
            path: str = "/".join(directories.split("/")[:i+1])
            if not exists(directory):
                makedirs(path, exist_ok=True)
            if directory.isdigit() and int(directory) == self.user_id:
                name_file_name: str = f"{path}/user_name.json"
                with open(name_file_name, "w") as file:
                    file.write(json.dumps(
                        {"user_name": self.user_name,
                         "user_id": self.user_id,
                         "starting_bonus_received": (
                             self.starting_bonus_received)
                         }))
                    pass

        # Create the save data file
        with open(self.file_name, "w"):
            pass

    def save(self, key: str, value: str) -> None:
        if not exists(self.file_name):
            self.create()

        with open(self.file_name, "w") as f:
            f.write(json.dumps({key: value}))

    def load(self, key: str) -> str | None:
        if not exists(self.file_name):
            return None

        all_data: Dict[str, str] = {}
        with open(self.file_name, "r") as file:
            for line in file:
                data: Dict[str, str] = json.loads(line)
                all_data.update(data)
            return all_data[key]
# endregion

# region Bonus die button
class StartingBonusView(View):
    def __init__(self,
                invoker: User | Member,
                starting_bonus_awards: Dict[int, int],
                save_data: UserSaveData,
                log: Log,
                interaction: Interaction) -> None:
        super().__init__(timeout=5)
        self.invoker: User | Member = invoker
        self.invoker_id: int = invoker.id
        self.starting_bonus_awards: Dict[int, int] = starting_bonus_awards
        self.save_data: UserSaveData = save_data
        self.log: Log = log
        self.interaction: Interaction = interaction
        self.button_clicked: bool = False
        self.die_button: Button[View] = Button(
            disabled=False,
            emoji="🎲",
            custom_id="starting_bonus_die")
        self.die_button.callback = self.on_button_click
        self.add_item(self.die_button)

    async def on_button_click(self, interaction: Interaction) -> None:
        clicker_id: int = interaction.user.id
        if clicker_id != self.invoker_id:
            await interaction.response.send_message(
                "You cannot role the die for someone else!", ephemeral=True)
        else:
            self.button_clicked = True
            self.die_button.disabled = True
            await interaction.response.edit_message(
                view=self)
            
            die_roll: int = random.randint(1, 6)
            starting_bonus: int = self.starting_bonus_awards[die_roll]
            message: str = (
                f"You rolled a {die_roll} and won {starting_bonus} {coins}!\n"
                "You may now play on the slot machines. Good luck!")
            await interaction.followup.send(message)
            del message
            await add_block_transaction(
                blockchain=blockchain,
                sender=CASINO_HOUSE_ID,
                receiver=self.invoker,
                amount=starting_bonus,
                method="starting_bonus"
            )
            self.save_data.save("starting_bonus_received", "True")
            last_block_timestamp: float | None = get_last_block_timestamp()
            if last_block_timestamp is None:
                print("ERROR: Could not get last block timestamp.")
                await terminate_bot()
            log.log(
                line=(f"{self.invoker} ({self.invoker_id}) won "
                    f"{starting_bonus} {coins} from the starting bonus."),
                timestamp=last_block_timestamp)
            self.stop()

    async def on_timeout(self) -> None:
        self.die_button.disabled = True
        message = ("You took too long to roll the die. When you're "
                    "ready, you may run the command again.")
        await self.interaction.edit_original_response(content=message,
                                                    view=self)
# endregion

# region Slots buttons
class SlotMachineView(View):
    def __init__(self,
                invoker: User | Member,
                slot_machine: SlotMachine,
                wager: int,
                interaction: Interaction) -> None:
        super().__init__(timeout=3)
        self.current_reel_number: int = 1
        self.reels_stopped: int = 0
        self.invoker: User | Member = invoker
        self.invoker_id: int = invoker.id
        self.slot_machine: SlotMachine = slot_machine
        self.wager: int = wager
        # TODO Move message variables to global scope
        self.empty_space: LiteralString = "\N{HANGUL FILLER}" * 11
        self.message_header: str = f"### {Coin} Slot Machine\n"
        self.message_reel_status: str = "The reels are spinning..."
        self.message_collect_screen: str = (f"-# Coin: {wager}\n"
                                            f"{self.empty_space}\n"
                                            f"{self.empty_space}")
        self.reels_results_row: str = f"🔳\t\t🔳\t\t🔳"
        self.message: str = (f"{self.message_header}\n"
                             f"{self.message_collect_screen}\n"
                             f"{self.message_reel_status}\n"
                             "\n"
                             f"{self.empty_space}")
        self.awards: (
            Dict[str, Dict[str, int | float]]) = cast(
                Dict[str, Dict[str, int | float]],
            self.slot_machine.configuration["awards"])
        self.interaction: Interaction = interaction
        blank_emoji: PartialEmoji = PartialEmoji.from_str("🔳")
        self.reels_results: Dict[
            str,
            Dict[str, str | int | float | PartialEmoji]]
        self.reels_results = (
            {
                "1":
                {"emoji": blank_emoji},
                
                "2":
                {"emoji": blank_emoji},
                
                "3":
                {"emoji": blank_emoji}
            }
        )
        self.button_clicked: bool = False
        self.stop_reel_buttons: List[Button[View]] = []
        # Create stop reel buttons
        for i in range(1, 4):
            button: Button[View] = Button(
                disabled=False,
                label="STOP",
                custom_id=f"stop_reel_{i}"
            )
            button.callback = lambda interaction, button_id=f"stop_reel_{i}": (
                self.on_button_click(interaction, button_id)
            )
            self.stop_reel_buttons.append(button)
            self.add_item(button)

    async def invoke_reel_stop(self, button_id: str) -> None:
        """
        Stops a reel and edits the message with the result.
        """
        # reel_number: int = self.current_reel_number
        # Map button IDs to reel key names
        reel_stop_button_map: Dict[str, str] = {
            "stop_reel_1": "1",
            "stop_reel_2": "2",
            "stop_reel_3": "3"
        }
        # Pick reel based on button ID
        reel_number: str = reel_stop_button_map[button_id]
        reel_name = str(reel_number)
        # Stop the reel and get the symbol
        symbol_name: str = self.slot_machine.stop_reel(reel=reel_name)
        # Get the emoji for the symbol (using the awards dictionary)
        symbol_emoji_name: str = cast(str, 
                                      self.awards[symbol_name]["emoji_name"])
        symbol_emoji_id: int = cast(int, 
                                    self.awards[symbol_name]["emoji_id"])
        # Create a PartialEmoji object (for the message)
        symbol_emoji: PartialEmoji = PartialEmoji(name=symbol_emoji_name,
                                                id=symbol_emoji_id)
        # Copy keys and values from the appropriate sub-dictionary in awards
        symbol_properties: Dict[str, str | int | float | PartialEmoji]
        symbol_properties = {**self.awards[symbol_name]}
        symbol_properties["name"] = symbol_name
        symbol_properties["emoji"] = symbol_emoji
        # Add the emoji to the result
        self.reels_results[reel_number] = symbol_properties
        self.reels_stopped += 1
        reel_status: str = (
            "The reels are spinning..." if self.reels_stopped < 3 else
            "The reels have stopped.")
        empty_space: LiteralString = "\N{HANGUL FILLER}" * 11
        self.message_reel_status = reel_status
        self.message_results_row: str = (
            f"{self.reels_results['1']['emoji']}\t\t"
            f"{self.reels_results['2']['emoji']}\t\t"
            f"{self.reels_results['3']['emoji']}")
        self.message = (f"{self.message_header}\n"
                        f"{self.message_collect_screen}\n"
                        f"{reel_status}\n"
                        f"{self.empty_space}\n"
                        f"{self.message_results_row}\n"
                        f"{empty_space}")
        
    # stop_button_callback
    async def on_button_click(self,
                            interaction: Interaction,
                            button_id: str) -> None:
        """
        Events to occur when a stop reel button is clicked.
        """
        clicker_id: int = interaction.user.id
        if clicker_id != self.invoker_id:
            await interaction.response.send_message(
                "Someone else is playing this slot machine. Please take "
                "another one.", ephemeral=True)
        else:
            self.button_clicked = True
            if self.timeout is not None and self.reels_stopped != 3:
                # Increase the timeout
                self.timeout += 1
            # Turn the clickable button into a disabled button,
            # stop the corresponding reel and edit the message with the result
            self.stop_reel_buttons[int(button_id[-1]) - 1].disabled = True
            # print(f"Button clicked: {button_id}")
            # The self.halt_reel() method updates self.message
            await self.invoke_reel_stop(button_id=button_id)
            await interaction.response.edit_message(content=self.message,
                                                    view=self)
            if self.reels_stopped == 3:
                self.stop()

    async def on_timeout(self) -> None:
        """
        Events to occur when the view times out.
        """
        if self.reels_stopped == 3:
            return
        
        # IMPROVE Add per-reel consecutive timers
        # (so that the invoker can click button 2 and 3 after button 1's
        # timer has run out)
        # Disable all buttons
        unclicked_buttons: List[str] = []
        for button in self.stop_reel_buttons:
            if not button.disabled:
                button_id: str = cast(str, button.custom_id)
                unclicked_buttons.append(button_id)
                button.disabled = True
            
        # Stop the remaining reels
        for button_id in unclicked_buttons:
            await self.invoke_reel_stop(button_id=button_id)
            await self.interaction.edit_original_response(
                content=self.message,
                view=self)
            if self.reels_stopped < 3:
                await asyncio.sleep(1)
        # The self.halt_reel() method stops the view if
        # all reels are stopped
# endregion

# region Flask funcs


def start_flask_app_waitress() -> None:
    global waitress_process

    def stream_output(pipe: TextIO, prefix: str) -> None:
        # Receive output from the Waitress subprocess
        for line in iter(pipe.readline, ''):
            # print(f"{prefix}: {line}", end="")
            print(f"{line}", end="")
        if hasattr(pipe, 'close'):
            pipe.close()

    print("Starting Flask app with Waitress...")
    program = "waitress-serve"
    app_name = "sb_blockchain"
    host = "*"
    # Use the environment variable or default to 8000
    port: str = os_environ.get("PORT", "8080")
    command: List[str] = [
        program,
        f"--listen={host}:{port}",
        f"{app_name}:app"
    ]
    waitress_process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("Flask app started with Waitress.")

    # Start threads to read output from the subprocess
    threading.Thread(
        target=stream_output,
        args=(waitress_process.stdout, "STDOUT"),
        daemon=True
    ).start()
    threading.Thread(
        target=stream_output,
        args=(waitress_process.stderr, "STDERR"),
        daemon=True
    ).start()


def start_flask_app() -> None:
    # For use with the Flask development server
    print("Starting flask app...")
    try:
        sb_blockchain.app.run(port=5000, debug=True, use_reloader=False)
    except Exception as e:
        print(f"Error running Flask app: {e}")
# endregion

# region CP start


def start_checkpoints(limit: int = 10) -> Dict[int, ChannelCheckpoints]:
    all_checkpoints: dict[int, ChannelCheckpoints] = {}
    print("Starting checkpoints...")
    channel_id: int = 0
    channel_name: str = ""
    for guild in bot.guilds:
        guild_id: int = guild.id
        guild_name: str = guild.name
        print(f"Guild: {guild_name} ({guild_id})")
        for channel in guild.text_channels:
            channel_id = channel.id
            channel_name = channel.name
            print(f"Channel: {channel_name} ({channel_id})")
            all_checkpoints[channel_id] = ChannelCheckpoints(
                guild_name=guild_name,
                guild_id=guild_id,
                channel_name=channel_name,
                channel_id=channel_id,
                number=limit
            )
    print("Checkpoints started.")
    return all_checkpoints


# region Missed msgs


async def process_missed_messages() -> None:
    '''
    Process messages that were sent since the bot was last online.
    This does not process reaction to messages older than the last checkpoint
    (i.e. older than the last message sent before the bot went offline). That
    would require keeping track of every single message and reactions on the
    server in a database.
    '''
    global all_channel_checkpoints
    missed_messages_processed_message: str = "Missed messages processed."

    print("Processing missed messages...")

    for guild in bot.guilds:
        print("Fetching messages from "
              f"guild: {guild.name} ({guild.id})...")
        for channel in guild.text_channels:
            print("Fetching messages from "
                  f"channel: {channel.name} ({channel.id})...")
            channel_checkpoints: List[Dict[str, int]] | None = (
                all_channel_checkpoints[channel.id].load())
            if channel_checkpoints is not None:
                print(f"Channel checkpoints loaded.")
            else:
                print("No checkpoints could be loaded.")
            new_channel_messages_found: int = 0
            fresh_last_message_id: int | None = None
            checkpoint_reached: bool = False
            # Fetch messages from the channel (reverse chronological order)
            async for message in channel.history(limit=None):
                message_id: int = message.id
                if new_channel_messages_found == 0:
                    # The first message found will be the last message sent
                    # This will be used as the checkpoint
                    fresh_last_message_id = message_id
                # print(f"{message.author}: {message.content} ({message_id}).")
                if channel_checkpoints is not None:
                    for checkpoint in channel_checkpoints:
                        if message_id == checkpoint["last_message_id"]:
                            print("Channel checkpoint reached.")
                            checkpoint_reached = True
                            break
                    if checkpoint_reached:
                        break
                    new_channel_messages_found += 1
                    for reaction in message.reactions:
                        async for user in reaction.users():
                            # print(f"Reaction found: {reaction.emoji}: {user}.")
                            # print(f"Message ID: {message_id}.")
                            # print(f"{message.author}: {message.content}")
                            sender: Member | User = user
                            receiver: User | Member = message.author
                            emoji: PartialEmoji | Emoji | str = reaction.emoji
                            await process_reaction(emoji, sender, receiver)
            print("Messages from "
                  f"channel {channel.name} ({channel.id}) fetched.")
            if fresh_last_message_id is None:
                print("WARNING: No channel messages found.")
            else:
                if new_channel_messages_found > 0:
                    # TODO Only save checkpoint if we read any messages beyond
                    # the already saved checkpoint
                    print(f"Saving checkpoint: {fresh_last_message_id}")
                    all_channel_checkpoints[channel.id].save(
                        fresh_last_message_id)
                else:
                    print("Will not save checkpoint for this channel because "
                          "no new messages were found.")
        print(f"Messages from guild {guild.id} ({guild}) fetched.")
    print(missed_messages_processed_message)

# endregion

# region Coin reaction


async def process_reaction(emoji: PartialEmoji | Emoji | str,
                           sender: Member | User,
                           receiver: Member | User | None = None,
                           receiver_id: int | None = None) -> None:
    # TODO Add "if reaction.message.author.id != user.id" to prevent self-mining

    emoji_id: int | str | None = 0
    match emoji:
        case Emoji():
            emoji_id = emoji.id
        case PartialEmoji() if emoji.id is not None:
            emoji_id = emoji.id
        case PartialEmoji():
            return
        case str():
            return
    if emoji_id == COIN_EMOJI_ID:

        if receiver is None:
            # Get receiver from id
            if receiver_id is not None:
                receiver = await bot.fetch_user(receiver_id)
            else:
                print("ERROR: Receiver is None.")
                return
        else:
            receiver_id = receiver.id

        sender_id: int = sender.id

        print(f"{sender} ({sender_id}) is mining 1 {coin} "
              f"for {receiver} ({receiver_id})...")
        await add_block_transaction(
            blockchain=blockchain,
            sender=sender,
            receiver=receiver,
            amount=1,
            method="reaction"
        )

        # Log the mining
        last_block_timestamp: float | None = get_last_block_timestamp()
        if last_block_timestamp is None:
            print("ERROR: Could not get last block timestamp.")
            await terminate_bot()

        try:
            mined_message: str = (f"{sender} ({sender_id}) mined 1 {coin} "
                                  f"for {receiver} ({receiver_id}).")
            log.log(line=mined_message, timestamp=last_block_timestamp)
        except Exception as e:
            print(f"Error logging mining: {e}")
            await terminate_bot()

        chain_validity: bool | None = None
        try:
            print("Validating blockchain...")
            chain_validity = blockchain.is_chain_valid()
        except Exception as e:
            # TODO Revert blockchain to previous state
            print(f"Error validating blockchain: {e}")
            chain_validity = False

        if chain_validity is False:
            await terminate_bot()
# endregion

# region Get timestamp


def get_last_block_timestamp() -> float | None:
    last_block_timestamp: float | None = None
    try:
        # Get the last block's timestamp for logging
        last_block: None | sb_blockchain.Block = blockchain.get_last_block()
        if last_block is not None:
            last_block_timestamp = last_block.timestamp
            del last_block
        else:
            print("ERROR: Last block is None.")
            return None
    except Exception as e:
        print(f"ERROR: Error getting last block: {e}")
        return None
    return last_block_timestamp


# endregion

# region Add tx block


async def add_block_transaction(
    blockchain: sb_blockchain.Blockchain,
    sender: Member | User | int,
    receiver: Member | User | int,
    amount: int,
    method: str
) -> None:
    if isinstance(sender, int):
        sender_id = sender
    else:
        sender_id: int = sender.id
    if isinstance(receiver, int):
        receiver_id = receiver
    else:
        receiver_id: int = receiver.id
    sender_id_unhashed: int = sender_id
    receiver_id_unhashed: int = receiver_id
    sender_id_hash: str = (
        sha256(str(sender_id_unhashed).encode()).hexdigest())
    receiver_id_hash: str = (
        sha256(str(receiver_id_unhashed).encode()).hexdigest())
    print("Adding transaction to blockchain...")
    try:
        data: List[Dict[str, sb_blockchain.TransactionDict]] = (
            [{"transaction": {
                "sender": sender_id_hash,
                "receiver": receiver_id_hash,
                "amount": amount,
                "method": method
            }}])
        data_casted: List[str | Dict[str, sb_blockchain.TransactionDict]] = (
            cast(List[str | Dict[str, sb_blockchain.TransactionDict]], data))
        blockchain.add_block(data=data_casted, difficulty=0)
    except Exception as e:
        print(f"Error adding transaction to blockchain: {e}")
        await terminate_bot()
    print("Transaction added to blockchain.")
# endregion

# region Terminate bot


async def terminate_bot() -> NoReturn:
    print("Closing bot...")
    await bot.close()
    print("Bot closed.")
    print("Shutting down the blockchain app...")
    waitress_process.send_signal(signal.SIGTERM)
    waitress_process.wait()
    """ print("Shutting down blockchain flask app...")
    try:
        requests.post("http://127.0.0.1:5000/shutdown")
    except Exception as e:
        print(e) """
    await asyncio.sleep(1)  # Give time for all tasks to finish
    print("The script will now exit.")
    sys_exit(1)
# endregion

# region Guild list


def load_guild_ids(file_name: str = "data/guild_ids.txt") -> List[int]:
    print("Loading guild IDs...")
    # Create missing directories
    makedirs("file_name", exist_ok=True)
    guild_ids: List[int] = []
    read_mode: str = "a+"
    if not exists(file_name):
        read_mode = "w+"
    else:
        read_mode = "r+"
    with open(file_name, read_mode) as file:
        for line in file:
            guild_id = int(line.strip())
            print(f"Adding guild ID {guild_id} from file to the list...")
            guild_ids.append(guild_id)
        for guild in bot.guilds:
            guild_id: int = guild.id
            if not guild_id in guild_ids:
                print(f"Adding guild ID {guild_id} "
                      "to the list and the file...")
                file.write(f"{guild_id}\n")
                guild_ids.append(guild_id)
    print("Guild IDs loaded.")
    return guild_ids
# endregion

# region Flask
if __name__ == "__main__":
    print("Starting blockchain flask app thread...")
    try:
        flask_thread = threading.Thread(target=start_flask_app_waitress)
        flask_thread.daemon = True  # Set the thread as a daemon thread
        flask_thread.start()
        print("Flask app thread started.")
    except Exception as e:
        print(f"Error starting Flask app thread: {e}")
    sleep(1)

    print(f"Initializing blockchain...")
    try:
        blockchain = sb_blockchain.Blockchain()
        print(f"Blockchain initialized.")
    except Exception as e:
        print(f"Error initializing blockchain: {e}")
        print("This script will be terminated.")
        sys_exit(1)
# endregion

# region Init
print("Starting bot...")

print("Loading bot configuration...")
configuration = BotConfiguration()
coin: str = configuration.coin
Coin: str = configuration.Coin
coins: str = configuration.coins
Coins: str = configuration.Coins
COIN_EMOJI_ID: int = configuration.coin_emoji_id
CASINO_HOUSE_ID: int = configuration.casino_house_id
ADMINISTRATOR_ID: int = configuration.administrator_id
slot_machine = SlotMachine()
print("Bot configuration loaded.")

print("Initializing log...")
log = Log(time_zone="Canada/Central")
print("Log initialized.")


@bot.event
async def on_ready() -> None:
    print("Bot started.")

    global all_channel_checkpoints
    all_channel_checkpoints = (
        start_checkpoints(limit=channel_checkpoint_limit))

    # await process_missed_messages()

    # global guild_ids
    # guild_ids = load_guild_ids()
    print(f"Guild IDs: {guild_ids}")
    for guild in bot.guilds:
        print(f"- {guild.name} ({guild.id})")

    # Sync the commands to Discord
    print("Syncing global commands...")
    try:
        await bot.tree.sync()
        print(f"Synced commands for bot {bot.user}.")
        print(f"Bot is ready!")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# endregion


# region Message
@bot.event
async def on_message(message: Message) -> None:
    global all_channel_checkpoints
    channel_id: int = message.channel.id

    if channel_id in all_channel_checkpoints:
        all_channel_checkpoints[channel_id].save(message.id)
    else:
        # If a channel is created while the bot is running, we will likely end
        # up here.
        # Add a new instance of ChannelCheckpoints to
        # the all_channel_checkpoints dictionary for this new channel.
        guild: Guild | None = message.guild
        if guild is None:
            print("ERROR: Guild is None.")
            administrator: str = (
                (await bot.fetch_user(ADMINISTRATOR_ID)).mention)
            await message.channel.send("An error occurred. "
                                       f"{administrator} pls fix.")
            return
        guild_name: str = guild.name
        guild_id: int = guild.id
        channel = message.channel
        if isinstance(channel, TextChannel):
            channel_name: str = channel.name
            all_channel_checkpoints[channel_id] = ChannelCheckpoints(
                guild_name=guild_name,
                guild_id=guild_id,
                channel_name=channel_name,
                channel_id=channel_id
            )
        else:
            print("ERROR: Channel is not a text channel.")
            administrator: str = (
                (await bot.fetch_user(ADMINISTRATOR_ID)).mention)
            await message.channel.send("An error occurred. "
                                       f"{administrator} pls fix.")
            return

# endregion


# region Reaction
@bot.event
async def on_raw_reaction_add(payload: RawReactionActionEvent) -> None:
    # `payload` is an instance of the RawReactionActionEvent class from the
    # discord.raw_models module that contains the data of the reaction event.
    if payload.guild_id is None:
        return

    if payload.event_type == "REACTION_ADD":
        if payload.message_author_id is None:
            return

        # Look for slot machine reactions
        message_id: int = payload.message_id
        reacter_id: int = payload.user_id
        if message_id in starting_bonus_messages_waiting:
            if (payload.emoji.name == "🎲" and
                    (starting_bonus_messages_waiting[message_id].invoker_id
                     == reacter_id)):
                print("Die rolled!")

        # Look for coin emoji
        if payload.emoji.id is None:
            return
        sender: Member | None = payload.member
        if sender is None:
            print("ERROR: Sender is None.")
            return
        receiver_user_id: int = payload.message_author_id
        await process_reaction(emoji=payload.emoji,
                               sender=sender,
                               receiver_id=receiver_user_id)
# endregion


# region /transfer
@bot.tree.command(name="transfer",
                  description=f"Transfer {coins} to another user")
@app_commands.describe(amount=f"Amount of {coins} to transfer",
                       user=f"User to transfer the {coins} to")
async def transfer(interaction: Interaction, amount: int, user: Member) -> None:
    """
    Transfer a specified amount of coins to another user.

    Args:
        interaction (Interaction): The interaction object representing the
        command invocation.
    """
    sender: User | Member = interaction.user
    sender_id: int = sender.id
    receiver: Member = user
    receiver_id: int = receiver.id
    print(f"User {sender_id} is requesting to transfer {amount} {coins} to "
          f"user {receiver_id}...")
    balance: int | None = None
    try:
        balance = blockchain.get_balance(user_unhashed=sender_id)
    except Exception as e:
        print(f"Error getting balance for user {sender} ({sender_id}): {e}")
        administrator: str = (await bot.fetch_user(ADMINISTRATOR_ID)).mention
        await interaction.response.send_message("Error getting balance."
                                                f"{administrator} pls fix.")
    if balance is None:
        print(f"Balance is None for user {sender} ({sender_id}).")
        await interaction.response.send_message(f"You have 0 {coins}.")
        return
    if balance < amount:
        print(f"{sender} ({sender_id}) does not have enough {coins} to "
              f"transfer {amount} to {sender} ({sender_id}). "
              f"Balance: {balance}.")
        await interaction.response.send_message(f"You do not have enough "
                                                f"{coins}. You have {balance} "
                                                f"{coins}.")
        return
    await add_block_transaction(
        blockchain=blockchain,
        sender=sender,
        receiver=receiver,
        amount=amount,
        method="transfer"
    )
    last_block: sb_blockchain.Block | None = blockchain.get_last_block()
    if last_block is None:
        print("ERROR: Last block is None.")
        administrator: str = (await bot.fetch_user(ADMINISTRATOR_ID)).mention
        await interaction.response.send_message("Error transferring coins. "
                                                f"{administrator} pls fix.")
        await terminate_bot()
    timestamp: float = last_block.timestamp
    log.log(line=f"{sender} ({sender_id}) transferred {amount} {coins} "
            f"to {receiver} ({receiver_id}).",
            timestamp=timestamp)
    await interaction.response.send_message(f"{sender.mention} transferred "
                                            f"{amount} {coins} "
                                            f"to {receiver.mention}.")
# endregion

# region /balance


@bot.tree.command(name="balance", description="Check your balance")
@app_commands.describe(user="User to check the balance")
async def balance(interaction: Interaction, user: Member | None = None) -> None:
    """
    Check the balance of a user. If no user is specified, the balance of the
    user who invoked the command is checked.

    Args:
        interaction (Interaction): The interaction object representing the
        command invocation.

        user (str, optional): The user to check the balance. Defaults to None.
    """
    user_to_check: Member | str
    if user is None:
        user_to_check = interaction.user.mention
        user_id: int = interaction.user.id
    else:
        user_to_check = user.mention
        user_id: int = user.id

    user_id_hash: str = sha256(str(user_id).encode()).hexdigest()
    balance: int | None = blockchain.get_balance(user=user_id_hash)
    if balance is None:
        await interaction.response.send_message(f"{user_to_check} has 0 "
                                                f"{coins}.")
    elif balance == 1:
        await interaction.response.send_message(f"{user_to_check} has 1 "
                                                f"{coin}.")
    else:
        await interaction.response.send_message(f"{user_to_check} has "
                                                f"{balance} {coins}.")
# endregion
# region /reels


@bot.tree.command(name="reels",
                  description="Design the slot machine reels")
@app_commands.describe(add_symbol="Add a symbol to the reels")
@app_commands.describe(amount="Amount of symbols to add")
@app_commands.describe(remove_symbol="Remove a symbol from the reels")
@app_commands.describe(reel="The reel to modify")
@app_commands.describe(report="Report the current configuration")
async def reels(interaction: Interaction,
                add_symbol: str | None = None,
                remove_symbol: str | None = None,
                amount: int | None = None,
                reel: str | None = None,
                report: bool | None = None) -> None:
    """
    Design the slot machine reels by adding and removing symbols.

    Args:
        interaction (Interaction): The interaction object representing the
        command invocation.

        add_symbol (str, optional): add_symbol a symbol to the reels.
        Defaults to None.

        remove_symbol (str, optional): Remove a symbol from the reels.
        Defaults to None.
    """
    # XXX
    # TODO Calculate RTP
    # TODO Set max amount of symbols
    # Check if user has the necessary role
    invoker: User | Member = interaction.user
    invoker_roles: List[Role] = cast(Member, invoker).roles
    administrator_role: Role | None = (
        utils.get(invoker_roles, name="Administrator"))
    technician_role: Role | None = (
        utils.get(invoker_roles, name="Slot Machine Technician"))
    if administrator_role is None and technician_role is None:
        # TODO Maybe let other users see the reels
        message: str = ("Only slot machine technicians may look at the reels.")
        await interaction.response.send_message(message)
        return
    if amount is None:
        if reel is None:
            amount = 3
        else:
            amount = 1
    new_reels: Dict[str, Dict[str, int]] = slot_machine.reels
    if add_symbol and remove_symbol:
        await interaction.response.send_message("You can only add or remove a "
                                                "symbol at a time.")
        return
    if add_symbol and reel is None:
        if amount % 3 != 0:
            await interaction.response.send_message("The amount of symbols to "
                                                    "add must be a multiple "
                                                    "of 3.")
            return
    elif add_symbol and reel:
        print(f"add_symboling symbol: {add_symbol}")
        print(f"Amount: {amount}")
        print(f"Reel: {reel}")
        if (reel in slot_machine.reels and
                add_symbol in slot_machine.reels[reel]):
            slot_machine.reels[reel][add_symbol] += amount
        else:
            print(f"Error: Invalid reel or symbol '{reel}' or '{add_symbol}'")
    if add_symbol:
        print(f"Adding symbol: {add_symbol}")
        print(f"Amount: {amount}")
        if add_symbol in slot_machine.reels['1']:
            per_reel_amount: int = int(amount / 3)
            new_reels['1'][add_symbol] += per_reel_amount
            new_reels['2'][add_symbol] += per_reel_amount
            new_reels['3'][add_symbol] += per_reel_amount

            slot_machine.reels = new_reels
            print(f"Added {per_reel_amount} {add_symbol} to each reel.")
        else:
            print(f"Error: Invalid symbol '{add_symbol}'")
        print(slot_machine.reels)
        # if amount
    elif remove_symbol and reel:
        print(f"Removing symbol: {remove_symbol}")
        print(f"Amount: {amount}")
        print(f"Reel: {reel}")
        if (reel in slot_machine.reels and
                remove_symbol in slot_machine.reels[reel]):
            slot_machine.reels[reel][remove_symbol] -= amount
        else:
            print(f"Error: Invalid reel '{reel}' or symbol '{remove_symbol}'")
    elif remove_symbol:
        print(f"Removing symbol: {remove_symbol}")
        print(f"Amount: {amount}")
        if remove_symbol in slot_machine.reels['1']:
            per_reel_amount: int = int(amount / 3)
            new_reels['1'][remove_symbol] -= per_reel_amount
            new_reels['2'][remove_symbol] -= per_reel_amount
            new_reels['3'][remove_symbol] -= per_reel_amount

            slot_machine.reels = new_reels
            print(f"Removed {per_reel_amount} {remove_symbol} from each reel.")
        else:
            print(f"Error: Invalid symbol '{remove_symbol}'")
        print(slot_machine.reels)

    print("Saving reels...")

    slot_machine.reels = new_reels
    slot_machine.calculate_total_return()
    new_reels = slot_machine.reels
    # print(f"Reels: {slot_machine.configuration}")
    print(f"Probabilities saved.")

    amount_of_symbols: int = slot_machine.count_symbols()
    reel_amount_of_symbols: int
    reels_table: str = ""
    for reel, symbols in new_reels.items():
        symbols_table: str = ""
        for symbol, amount in symbols.items():
            symbols_table += f"{symbol}: {amount}\n"
        reel_amount_of_symbols = sum(symbols.values())
        reels_table += (f"**Reel {reel}**\n"
                        f"{symbols_table}"
                        "\n**Total**\n"
                        f"{reel_amount_of_symbols}\n\n")
    probabilities: Dict[str, float] = slot_machine.probabilities
    probabilities_table: str = ""
    max_digits: int = 4
    lowest_number: float = float("0." + "0" * (max_digits - 1) + "1")
    for symbol, probability in probabilities.items():
        probability_display: str | None = None
        probability_percentage: float = probability * 100
        probability_rounded: float = round(probability_percentage, max_digits)
        if (probability == probability_rounded):
            probability_display = f"{str(probability_percentage)}%"
        elif probability_percentage > lowest_number:
            probability_display = "~{}%".format(
                str(round(probability_percentage, max_digits)))
        else:
            probability_display = f"<{str(lowest_number)}%"
        probabilities_table += f"{symbol}: {probability_display}\n"

    total_returns: Expr = slot_machine.calculate_total_return()
    wagers: List[int] = [
        1, 2, 5, 10, 50, 100, 500, 1000, 10000, 100000, 1000000]
    rtp_dict = {}
    rtp_display: str | None = None
    for wager in wagers:
        rtp = (
            slot_machine.calculate_rtp(wager))
        rtp_percentage = Mul(rtp, 100.0)
        rtp_rounded = round(rtp_percentage, max_digits)
        if rtp == rtp_rounded:
            rtp_display = f"{str(rtp_percentage)}%"
        elif simplify(rtp_percentage) > lowest_number:
            rtp_display = "~{}%".format(str(rtp_rounded))
        else:
            rtp_display = f"<{str(lowest_number)}%"
        rtp_dict[wager] = rtp_display

    rtp_table: str = ""
    for wager, rtp in rtp_dict.items():
        rtp_table += f"{wager}: {rtp}\n"

    message: str = ("### Reels\n"
                    f"{reels_table}\n"
                    "### Symbols total\n"
                    f"{amount_of_symbols}\n\n\n"
                    "### Probabilities\n"
                    f"{probabilities_table}\n\n"
                    "### Total returns\n"
                    f"{str(total_returns).replace("*", "\\*")}%\n"
                    '-# "W" means wager\n\n'
                    "### RTP\n"
                    "Wager: RTP\n"
                    f"{rtp_table}")
    # TODO Win/lose and RTP multiplier doesn't seem right
    # TODO Per symbol RTP
    await interaction.response.send_message(message)


# endregion


# region /slots


@bot.tree.command(name="slots",
                  description="Play on a slot machine")
@app_commands.describe(wager="Amount of coins to wager")
async def slots(interaction: Interaction, wager: int | None = None) -> None:
    """
    Command to play a slot machine.

    Args:
        interaction (Interaction): The interaction object representing the
        command invocation.
    """
    # TODO Ensure you cannot wager 0 coins or negative
    if wager is None:
        wager = 1
    # TODO Ensure you cannot play if your balance is below wager
    # TODO Ensure you cannot play if you have a pending game
    user: User | Member = interaction.user
    user_id: int = user.id
    user_name: str = user.name
    save_data: UserSaveData = (
        UserSaveData(user_id=user_id, user_name=user_name))
    starting_bonus_received: bool = (
        save_data.load("starting_bonus_received") == "True")

    if not starting_bonus_received:
        # Send message to inform user of starting bonus
        starting_bonus_awards: Dict[int, int] = {
            1: 50, 2: 100, 3: 200, 4: 300, 5: 400, 6: 500}
        starting_bonus_table: str = "> **Die roll**\t**Amount**\n"
        for die_roll, amount in starting_bonus_awards.items():
            starting_bonus_table += f"> {die_roll}\t\t\t\t{amount}\n"
        # TODO Divide into separate messages
        message: str = (f"Welcome to the {Coin} Casino! This seems to be your "
                        "first time here.\n"
                        "A standard 6-sided die will decide your starting "
                        "bonus.\n"
                        "The possible outcomes are displayed below.\n\n"
                        f"{starting_bonus_table}")

        starting_bonus_view = StartingBonusView(invoker=user,
                                 starting_bonus_awards=starting_bonus_awards,
                                 save_data=save_data,
                                 log=log,
                                 interaction=interaction)
        await interaction.response.send_message(content=message,
                                                view=starting_bonus_view)
        await starting_bonus_view.wait()
        del starting_bonus_view
    """ else:
        print("Starting bonus already received.") """


    slot_machine_view = SlotMachineView(invoker=user,
                           slot_machine=slot_machine,
                           wager=wager,
                           interaction=interaction)
    # TODO Add animation
    # Workaround for Discord stripping trailing whitespaces
    empty_space: LiteralString = "\N{HANGUL FILLER}" * 11
    
    slots_message: str = (f"### {Coin} Slot Machine\n"
               f"-# Coin: {wager}\n"
               f"{empty_space}\n"
               f"{empty_space}\n"
               "The reels are spinning...\n"
               "\n"
               f"🔳\t\t🔳\t\t🔳\n"
               f"{empty_space}")
    
    await interaction.response.send_message(content=slots_message,
                                            view=slot_machine_view)
    timed_out: bool = await slot_machine_view.wait()
    if timed_out:
        # Wait until all reels have stopped
        await asyncio.sleep(3)
    del timed_out
    
    def generate_coin_label(number: int) -> str:
        if number == 1:
            return coin
        else:
            return coins

    # Get results
    results: Dict[str, Dict[str, str | int | float | PartialEmoji]] = slot_machine_view.reels_results
    
    # Determine transfer amount
    # and generate outcome messages and log lines
    slot_machine_header: str = slot_machine_view.message_header
    slot_machine_results_row: str = slot_machine_view.message_results_row
    del slot_machine_view
    award_name: str
    award_name_friendly: str
    win_money: int
    transfer_amount: int
    if wager == 1:
        # The jackpot game fee was not paid
        main_game_wager = 1
    else:
        # Subtract the jackpot game fee
        main_game_wager: int = wager - 1
    award_name, award_name_friendly, win_money = (
        slot_machine.calculate_award_money(wager=main_game_wager, results=results))
    print(f"award_name: {award_name}")
    print(f"award_name_friendly: {award_name_friendly}")
    print(f"profit: {win_money}")
    outcome_message_1: str | None = None
    outcome_message_2: str | None = None
    profited: bool = False
    if award_name == "standard_lose":
        transfer_amount = 1
        if wager != 1:
            # Subtract the jackpot fee
            money_back: int = wager - 1
            outcome_message_1 = (f"-# You collect "
                               f"{money_back} {coins}.")
        coin_label: str = generate_coin_label(transfer_amount)
        log_line: str = (f"{user_name} ({user_id}) lost "
                         f"{transfer_amount} {coin_label} "
                         f"on the {Coin} slot machine.")
        profited = False
    elif award_name == "jackpot_fail":
        transfer_amount = 1
        jackpot_amount: int = slot_machine.jackpot
        log_line = f"{user_name} ({user_id}) lost {transfer_amount} {coin} slot machine."
        outcome_message_1 = (f"{award_name_friendly}! Unfortunately, you did "
                             f"not pay the jackpot fee of 1 {coin}, meaning "
                             f"that you did not win "
                             f"the jackpot of {jackpot_amount} {coins}. "
                             "Better luck next time!")
        profited = False
    elif award_name == "lose_wager":
        coin_label = generate_coin_label(wager)
        outcome_message_1 = (f"You lost your entire "
                             f"bet of {wager} {coin_label}. "
                             "Better luck next time!")
        log_line = (f"{user_name} ({user_id}) lost their entire wager "
                    f"of {wager} {coins} from "
                    f"the {award_name} ({award_name_friendly}) award on "
                    f"the {Coin} slot machine.")
        transfer_amount = wager
        profited = False
    else:
        # The rest of the possible awards are wins
        coin_label: str = generate_coin_label(win_money)
        outcome_message_1 = (f"{award_name_friendly}! "
                             f"You won {win_money} {coins}!")
        net_amount: int
        if wager == 1:
            # they keep their wager
            net_amount: int = win_money
            transfer_amount = win_money - 1
        else:
            net_amount = win_money - wager
            transfer_amount = win_money - 1
        print(f"wager: {wager}")
        money_back: int
        coin_label: str = generate_coin_label(net_amount)
        if (net_amount > 0):
            # TODO Maybe make small_win coin_profit 3 instead of 1
            money_back = net_amount
            print(f"money_back: {money_back}")
            outcome_message_2 = (f"-# You collect {money_back} {coins}.")
            log_line = (f"{user_name} ({user_id}) won "
                        f"the {award_name} ({award_name_friendly}) reward "
                        f"and gained {net_amount} {coin_label} on "
                        f"the {Coin} slot machine.")
            profited = True
        elif (net_amount == 0):
            profited = False
        else:
            # This can happen you win 1 coin and wagered 2 coins
            # XXX
            transfer_amount = wager - win_money
            log_line = (f"{user_name} ({user_id}) won "
                        f"the {award_name} ({award_name_friendly}) reward "
                        f"and lost {net_amount} {coin_label} on "
                        f"the {Coin} slot machine.")
            profited = False

    if outcome_message_1 or outcome_message_2:
        # Display outcome messages
        if not outcome_message_2:
            outcome_message_2 = empty_space
        slot_machine_collect_screen: str = (f"{outcome_message_1}\n"
                                            f"{outcome_message_2}")
        # edit original message
        slots_message_outcome: str = (f"{slot_machine_header}\n"
                                    f"{slot_machine_collect_screen}\n"
                                    f"{empty_space}\n"
                                    "The reels have stopped.\n"
                                    f"{empty_space}\n"
                                    f"{slot_machine_results_row}\n"
                                    f"{empty_space}")
        await interaction.edit_original_response(content=slots_message_outcome)
    
    # Transfer and log
    sender: User | Member | int
    receiver: User | Member | int
    log_timestamp: float = 0.0
    last_block_error = False
    if profited:
        sender = CASINO_HOUSE_ID
        receiver = user
    else:
        sender = user
        receiver = CASINO_HOUSE_ID
    if transfer_amount > 0:
        await add_block_transaction(
            blockchain=blockchain,
            sender=sender,
            receiver=receiver,
            amount=transfer_amount,
            method="slot_machine"
        )
        last_block_timestamp: float | None = get_last_block_timestamp()
        if last_block_timestamp is None:
            print("ERROR: Could not get last block timestamp.")
            log_timestamp = time()
            log_line += ("(COULD NOT GET LAST BLOCK TIMESTAMP; USING CURRENT TIME; "
                        "WILL NOT RESET JACKPOT)")
            last_block_error = True
        else:
            log_timestamp = last_block_timestamp
    else:
        log_timestamp = time()
    log.log(line=log_line, timestamp=log_timestamp)
    if last_block_error:
        await terminate_bot()

    if award_name == "jackpot":
        # Reset the jackpot
        awards: Dict[str, Dict[str, int | float]] = cast(Dict[str, Dict[str, int | float]], slot_machine.configuration["awards"])
        jackpot_seed: int = cast(int, awards["jackpot"]["coin_profit"])
        slot_machine.jackpot = jackpot_seed
    else:
        slot_machine.jackpot += 1
    

# endregion


# region Message
# Example slash command

@bot.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: Interaction) -> None:
    """
    Replies with Pong! The response is visible only to the user who invoked the
    command.

    Args:
        interaction (Interaction): The interaction object representing the
        command invocation.
    """
    await interaction.response.send_message("Pong!", ephemeral=True)
# endregion

# TODO Prevent self-mining
# TODO Track reaction removals
# TODO Add "hide" parameters to commands
# TODO Add transfer command
# TODO Add gamble command
# TODO Add help command

# region Main
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("Error: DISCORD_TOKEN is not set in the environment variables.")
# endregion
