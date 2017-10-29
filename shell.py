import glob
import sys
import pytoml as toml
from attr import attrs, attrib
from dice import roll_dice, roll_dice_expr
from initiative import TurnManager
from models import Character, Encounter, Monster


commands = {}

@attrs
class GameState:
    characters = attrib(default={})
    monsters = attrib(default={})
    encounter = attrib(default=None)
    tm = attrib(default=None)


class Command:

    keywords = ['command']

    def __init__(self, game):
        self.game = game
        for kw in self.keywords:
            commands[kw] = self
        print("Registered "+self.__class__.__name__)

    def do_command(self, *args):
        print("Nothing happens.")

    def show_help_text(self, keyword):
        if hasattr(self, 'help_text'):
            divider = "-" * len(keyword)
            print(self.help_text.format(**locals()))
        else:
            print("No help text available for: "+keyword)


class ListCommands(Command):

    keywords = ['commands']
    help_text = """{keyword}
{divider}
Summary: List available commands

Usage: {keyword}
"""

    def do_command(self, *args):
        print("Available commands:\n")
        for keyword in list(sorted(commands.keys())):
            print('*', keyword)
        print()


class Help(Command):

    keywords = ['help']
    help_text = """{keyword}
{divider}
Summary: Get help for a command.

Usage: {keyword} <command>
"""

    def do_command(self, *args):
        if not args:
            self.show_help_text('help')
            return

        keyword = args[0]
        command = commands.get(keyword)
        if not command:
            print("Unknown command: "+keyword)
            return
        command.show_help_text(keyword)

    def show_help_text(self, keyword):
        super().show_help_text(keyword)
        ListCommands.do_command(self, *[])


class Quit(Command):

    keywords = ['quit', 'exit']
    help_text = """{keyword}
{divider}
Summary: quit the shell

Usage: {keyword}
"""

    def do_command(self, *args):
        print("Goodbye!")
        sys.exit(1)


class Load(Command):

    keywords = ['load']
    help_text = """{keyword}
{divider}
Summary: Load stuff

Usage:
    {keyword} party
    {keyword} encounter
"""

    def do_command(self, *args):
        if not args:
            print("Load what?")
            return
        if args[0] == 'party':
            self.load_party()
        elif args[0] == 'encounter':
            self.load_encounter()

    def load_party(self):
        party = {}
        with open('party.toml', 'r') as fin:
            party = toml.load(fin)
        self.game.characters = \
                {x['name']: Character(**x) for x in party.values()}
        print("OK; loaded {} characters".format(len(party)))

    def load_encounter(self):
        available_encounter_files = glob.glob('encounters/*.toml')
        if not available_encounter_files:
            print("No available encounters found.")
            return
        print("Available encounters:\n")
        encounters = []
        for i, filename in enumerate(available_encounter_files, 1):
            encounter = Encounter(**toml.load(open(filename, 'r')))
            encounters.append(encounter)
            print(f"{i}: {encounter.name} ({encounter.location})")
        pick = input("\nLoad encounter: ")
        if not pick.isdigit():
            print("Invalid encounter.")
            return
        pick = int(pick) - 1
        if pick < 0 or pick > len(encounters):
            print("Invalid encounter.")
            return
        self.game.encounter = encounter = encounters[pick]
        print("Loaded encounter: "+encounter.name)

        for group in encounter.groups.values():
            available_monster_files = glob.glob('monsters/*.toml')
            monsters = []

            for filename in available_monster_files:
                monster = toml.load(open(filename, 'r'))
                if monster['name'] == group['monster']:
                    for i in range(group['count']):
                        monsters.append(Monster(**monster))
                    break

            for i in range(len(monsters)):
                if 'max_hp' in group and len(group['max_hp']) == len(monsters):
                    monsters[i].max_hp = group['max_hp'][i]
                    monsters[i].cur_hp = group['max_hp'][i]
                else:
                    monsters[i].max_hp = monsters[i]._max_hp
                    monsters[i].cur_hp = monsters[i].max_hp

                if monsters[i].name[0].islower():
                    monsters[i].name = monsters[i].name+str(i+1)
                self.game.monsters[monsters[i].name] = monsters[i]


class Show(Command):

    keywords = ['show']

    def do_command(self, *args):
        if not args:
            print("Show what?")
            return
        if args[0] == 'party':
            self.show_party()
        elif args[0] == 'monsters':
            self.show_monsters()
        elif args[0] == 'turn':
            self.show_turn()

    def show_party(self):
        party = list(sorted(self.game.characters.items()))
        for name, character in party:
            print(f"{name:20}\tHP: {character.cur_hp}/{character.max_hp}"
                    f"\tAC: {character.ac}\tPer: {character.perception}\t"
                    f"Status: {character.status}"
            )

    def show_monsters(self):
        monsters = list(sorted(self.game.monsters.items()))
        for name, monster in monsters:
            print(f"{name:20}\tHP: {monster.cur_hp}/{monster.max_hp}"
                    f"\tAC: {monster.ac}\tPer: {monster.perception}\t"
                    f"Status: {monster.status}"
            )

    def show_turn(self):
        if not self.game.tm:
            print("No turn in progress.")
            return
        elif not self.game.tm.cur_turn:
            print("No turn in progress.")
            return
        turn = self.game.tm.cur_turn
        print(f"Round: {turn[0]} Initiative: {turn[1]} Name: {turn[2].name}")


class Start(Command):

    keywords = ['start']

    def do_command(self, *args):
        self.game.tm = TurnManager()

        for monster in self.game.monsters.values():
            self.game.tm.add_combatant(monster, roll_dice(1, 20,
                modifier=monster.initiative_bonus))

        for character in self.game.characters.values():
            roll = input(f"Initiative for {character.name}: ")
            if not roll:
                roll = roll_dice(1, 20, modifier=character.initiative_modifier)
            elif roll.isdigit():
                roll = int(roll)
            self.game.tm.add_combatant(character, roll)

        print("\nBeginning combat with: ")
        for roll, combatants in self.game.tm.turn_order:
            for combatant in combatants:
                print(f"{roll}: {combatant.name}")

        self.game.tm.turns = self.game.tm.generate_turns()


class NextTurn(Command):

    keywords = ['next']

    def do_command(self, *args):
        if not self.game.tm:
            print("Combat hasn't started yet.")
            return
        turn = next(self.game.tm.turns)
        self.game.tm.cur_turn = turn
        Show.show_turn(self)


class Damage(Command):

    keywords = ['damage', 'hurt']

    def do_command(self, *args):
        target_name = args[0]
        amount = int(args[1])

        target = self.game.characters.get(target_name) or \
                self.game.monsters.get(target_name)
        if not target:
            print("Invalid target: "+target_name)
            return

        target.cur_hp -= amount


class Heal(Command):

    keywords = ['heal']

    def do_command(self, *args):
        target_name = args[0]
        amount = int(args[1])

        target = self.game.characters.get(target_name) or \
                self.game.monsters.get(target_name)
        if not target:
            print("Invalid target: "+target_name)
            return

        target.cur_hp += amount


def register_commands(game):
    ListCommands(game)
    Help(game)
    Quit(game)
    Load(game)
    Show(game)
    Start(game)
    NextTurn(game)
    Damage(game)
    Heal(game)


def main_loop(game):
    while True:
        try:
            user_input = input("> ").split()
            if not user_input:
                continue

            command = commands.get(user_input[0]) or None
            if not command:
                print("Unknown command.")
                continue

            command.do_command(*user_input[1:])
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == '__main__':
    game = GameState()
    register_commands(game)
    main_loop(game)
