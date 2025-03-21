# region Imports
# Standard Library
from typing import List, cast

# Third party
from discord import Guild, Interaction, Member, Role, User, utils

# Local
from core.global_state import coin, Coin

# region Get role


def get_role(interaction: Interaction,
             role_names: List[str] | str) -> Role | None:
    guild: Guild | None = interaction.guild
    if guild is None:
        print("ERROR: Guild is None.")
        return None

    requested_role: Role | None = None
    if isinstance(role_names, str):
        role_names_list: List[str] = [role_names]
    else:
        role_names_list = role_names
    for role_name in role_names_list:
        requested_role = utils.get(guild.roles, name=role_name)
        if requested_role is not None:
            break
    return requested_role
# endregion

# region Get IT officer


def get_cybersecurity_officer_role(interaction: Interaction) -> Role | None:
    role_names: List[str] = [
        f"{Coin} Security Officer", f"{Coin} security officer",
        f"{coin} security officer", f"{coin}_security_officer",
        f"{Coin} Casino Security Officer", f"{Coin} Casino security officer",
        f"{coin} Casino security officer", f"{coin}_casino_security_officer",
        "Information Security Officer", "Information security officer",
        "information security officer", "information_security_officer"
        "Computer Security Officer", "Computer security officer",
        "computer security officer", "computer_security_officer",
        "Cybersecurity Officer", "Cybersecurity officer",
        "cybersecurity officer", "cybersecurity_officer"]
    cybersecurity_officer: Role | None = get_role(interaction, role_names)
    return cybersecurity_officer
# endregion

# region AML Officer


def get_aml_officer_role(interaction: Interaction) -> Role | None:
    role_names: List[str] = [
        "Anti-Money Laundering Officer",
        "Anti-money laundering officer",
        "anti-money laundering officer",
        "anti_money_laundering_officer",
        "AML Officer", "AML officer" "aml_officer"]
    aml_officer: Role | None = get_role(interaction, role_names)
    return aml_officer


def test_invoker_is_aml_officer(interaction: Interaction) -> bool:
    invoker: User | Member = interaction.user
    invoker_roles: List[Role] = cast(Member, invoker).roles
    role_names: List[str] = [
        "Anti-Money Laundering Officer",
        "Anti-money laundering officer",
        "anti_money_laundering_officer",
        "AML Officer", "AML officer" "aml_officer"]
    aml_officer_role: Role | None = None
    for role_name in role_names:
        aml_officer_role = utils.get(invoker_roles, name=role_name)
        if aml_officer_role is not None:
            break
    del invoker, invoker_roles
    if aml_officer_role is None:
        return False
    else:
        return True
# endregion
